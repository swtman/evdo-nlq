"""
QueryPipeline — the heart of the backend.

This module owns ALL business logic for the NLQ pipeline. Route handlers in
`app/api/query.py` are intentionally kept as thin transport wrappers — they
receive an HTTP request and return an HTTP response, but every meaningful
decision (how to call the LLM, whether to retry, how to execute the query)
lives exclusively here.

THE PIPELINE IN ONE PICTURE
-----------------------------
User question (Greek/English)
  │
  ▼
[1] Build system prompt
    load ontology summary + load prompt template + fill placeholders
  │
  ▼
[2] LLM generates SPARQL  (streaming token-by-token in stream_events,
    │                       or full response in run/_generate_with_retry)
  │
  ▼
[3] Clean output (strip markdown fences if LLM added them despite instructions)
  │
  ├─── NOT_ANSWERABLE? ──→ stop here, return/yield the comment, skip GraphDB
  │
  ▼
[4] Validate SPARQL offline (rdflib, no network)
  │
  ├─── valid? ──→ proceed to GraphDB
  │
  ├─── invalid + retries left? ──→ build retry prompt, call LLM again → back to [3]
  │
  ├─── invalid + no retries left? ──→ proceed to GraphDB anyway (may fail there)
  │
  ▼
[5] Execute SPARQL against GraphDB (SPARQLWrapper HTTP call)
  │
  ▼
[6] Return / yield results + metadata (token counts, retry count)

TWO PATHS, SAME LOGIC
-----------------------
`stream_events()` — async streaming path used by `POST /query/stream`.
    Yields typed event objects one by one so the frontend can show the query
    being written in real time.

`run()` / `_generate_with_retry()` — synchronous path used by `POST /query`.
    Blocks until all phases complete, then returns a single PipelineResult.

Both paths share the same prompt construction, retry strategy, and clean/
validate/execute logic. The only difference is how results are delivered.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.config import settings
from app.grounding import build_grounding_hints
from app.llm.base import LLMProvider
from app.ontology.loader import load_summary
from app.prompts.examples_loader import select_few_shot
from app.prompts.loader import fill, load
from app.sparql.client import SparqlClient, validate_sparql

logger = logging.getLogger(__name__)

# Maximum number of corrective LLM calls after the first generation fails
# SPARQL validation. Total LLM calls per request: 1 (initial) + up to 2
# (retries) = up to 3. See ADR-004 for the rationale.
_MAX_RETRIES = 2


# ---------------------------------------------------------------------------
# Typed event objects — the streaming path yields these; the route handler
# maps them to SSE dicts. No SSE concerns live inside this module.
#
# WHAT IS A TYPED EVENT?
# Each event is a plain dataclass carrying only the data relevant to that
# moment in the pipeline. The route handler uses isinstance() to map each
# event type to the correct SSE format. Having separate types (instead of
# a single dict with a "type" key) means the type checker catches mistakes
# at development time rather than at runtime.
# ---------------------------------------------------------------------------


@dataclass
class TokenEvent:
    """One chunk of text received from the LLM during streaming.

    Yielded repeatedly during Phase 1 of stream_events(), once per token.
    The `token` field is whatever the provider's generator emits — for
    Claude/Gemini it is one or a few characters; for FakeProvider it is
    exactly one character (it calls iter() on the full string).

    The route handler maps this to SSE event name: `sparql_token`.
    """

    token: str


@dataclass
class RetryEvent:
    """Signals that SPARQL validation failed and a retry is about to happen.

    Yielded at the START of each retry cycle, before the corrective LLM call.
    This lets the frontend show a "retrying..." indicator immediately.

    Fields
    ------
    attempt : int
        Which retry this is, 1-based. First retry = 1, second = 2.
    error : str
        The rdflib parse error message from the failed SPARQL. This same
        string is injected into the retry prompt so the LLM knows what
        went wrong.

    The route handler maps this to SSE event name: `sparql_retry`.
    """

    attempt: int
    error: str


@dataclass
class CompleteEvent:
    """The final SPARQL string after all generation and retry attempts.

    Yielded exactly once, after Phase 2 (validate + retry) completes.
    `sparql` is the cleaned query that will be sent to GraphDB — or the
    `# NOT_ANSWERABLE: ...` comment if the question could not be answered.

    The route handler maps this to SSE event name: `sparql_complete`.
    """

    sparql: str


@dataclass
class ResultsEvent:
    """The data rows returned by GraphDB after executing the SPARQL query.

    Yielded once in Phase 3, after SparqlClient.execute() succeeds.
    NOT yielded on the NOT_ANSWERABLE fast path (GraphDB is never called).

    Fields
    ------
    columns : list[str]
        Variable names from the SELECT clause, e.g. ["title", "author"].
        These become column headers in the frontend table.
    rows : list[dict]
        One dict per result row. Keys are column names; values are strings
        (or None for unbound OPTIONAL variables).

    The route handler maps this to SSE event name: `results`.
    """

    columns: list[str]
    rows: list[dict]


@dataclass
class DoneEvent:
    """Final metadata event — always the last event yielded by stream_events().

    Carries a summary of the full request: which provider/model was used,
    total token costs (summed across the initial generation + any retries),
    and how many retries were needed.

    On the NOT_ANSWERABLE fast path: `retries` is 0, tokens reflect only
    the initial stream.

    The route handler maps this to SSE event name: `done`.
    """

    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    retries: int


# The union type of all possible events yielded by stream_events().
# Written as `A | B | C | ...` — Python reads this as "one of these types".
# The route handler's isinstance() chain exhausts all cases; the type checker
# will warn if a new event type is added but not handled there.
PipelineEvent = TokenEvent | RetryEvent | CompleteEvent | ResultsEvent | DoneEvent


# ---------------------------------------------------------------------------
# Result type for the synchronous path
# ---------------------------------------------------------------------------


@dataclass
class PipelineResult:
    """Structured return value from run() — the synchronous pipeline path.

    Fields mirror DoneEvent plus the actual query and result data. The route
    handler unpacks this directly into the QueryResponse Pydantic model via
    `QueryResponse(**result.__dict__)` — both have identical field names.
    """

    sparql: str
    columns: list[str]
    rows: list[dict]
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    retries: int


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class QueryPipeline:
    """Orchestrates the full NLQ pipeline for one request.

    DEPENDENCY INJECTION
    --------------------
    The pipeline never creates its own LLM provider or SPARQL client. It
    receives them as constructor arguments — (dependency injection). 
    The caller (`_make_pipeline()` in `app/api/query.py`) is
    responsible for constructing and passing in the right objects.

    Benefits:
    - Easy to test: pass a FakeProvider and a mock SparqlClient, no network.
    - Flexible: the provider and model can differ per request (chosen by the
      user via the UI dropdown).
    - No hidden global state inside this class.

    A new QueryPipeline is created for every HTTP request. Since __init__
    only stores references (no network calls, no file reads), this is free.
    """

    def __init__(
        self,
        provider: LLMProvider,
        sparql_client: SparqlClient,
        provider_name: str,
        model_name: str,
    ) -> None:
        """Store all injected dependencies. No side effects.

        Parameters
        ----------
        provider : LLMProvider
            The LLM to use for SPARQL generation. Satisfies the LLMProvider
            Protocol — could be ClaudeProvider, GeminiProvider, or FakeProvider.
        sparql_client : SparqlClient
            The HTTP client for sending validated queries to GraphDB.
        provider_name : str
            Raw provider name string from the request (e.g. "claude"). Stored
            only for inclusion in DoneEvent / PipelineResult metadata.
        model_name : str
            Raw model string from the request (e.g. "claude-haiku-4-5"). Same.
        """
        self._provider = provider
        self._sparql_client = sparql_client
        self._provider_name = provider_name
        self._model_name = model_name

    # ------------------------------------------------------------------
    # Internal: system prompt construction
    # ------------------------------------------------------------------

    def _build_system(self, question: str) -> str:
        """Build the filled system prompt for a given question.

        Centralises the prompt construction that was previously duplicated
        in run() and stream_events(). Uses prompt v5 (adds {grounding_hints}).

        When GROUNDING_ENABLED is False (env var), grounding_hints is set to ""
        so the prompt behaves identically to v4 — useful for A/B comparisons.

        Args:
            question: Raw user question, used by the grounding module to
                      resolve entity mentions and compute word stems.

        Returns:
            Filled system prompt string ready to pass to the LLM.
        """
        grounding_hints = (
            build_grounding_hints(question) if settings.grounding_enabled else ""
        )
        return fill(
            load("nl-to-sparql", 5),
            ontology_summary=load_summary(),
            few_shot_block=select_few_shot(k=8),
            grounding_hints=grounding_hints,
        )

    # ------------------------------------------------------------------
    # Public: synchronous path
    # ------------------------------------------------------------------

    def run(self, question: str) -> PipelineResult:
        """Run the full pipeline synchronously and return a PipelineResult.

        Used by `POST /query`. Blocks until all phases complete.

        PROMPT CONSTRUCTION
        -------------------
        1. load_summary() — reads prompts/ontology-summary.md (cached after
           first call; subsequent calls are instant memory reads).
        2. load("nl-to-sparql", 4) — extracts the # System section from
           prompts/nl-to-sparql-v4.md (also cached). This is the ACTIVE
           prompt template. v1-v3 are archived; v4 targets the post-2026-06-11
           EvdoGraph schema (evdx:Course = course offering, no programme layer).
        3. select_few_shot(k=6) — selects up to 6 representative
           (question, SPARQL) example pairs from prompts/examples.yaml,
           one per distinct query shape, formatted as a text block.
        4. fill(...) — substitutes {ontology_summary} and {few_shot_block}
           placeholders in the template. SPARQL curly braces in the examples
           are safe because fill() only matches {word} (no spaces).

        The filled string becomes the `system` argument to every LLM call.
        The `question` string becomes the `user` argument — it is never
        embedded in the system prompt for the main template.

        Parameters
        ----------
        question : str
            The user's natural-language question (Greek or English).

        Returns
        -------
        PipelineResult
            On the NOT_ANSWERABLE path: columns=[], rows=[], retries=0.
            On success: columns and rows from GraphDB, retries = number of
            corrective LLM calls made (0 if first attempt was valid).

        Raises
        ------
        RuntimeError
            If SparqlClient.execute() fails (GraphDB unreachable or rejects
            the query). The route handler in query.py maps this to HTTP 502.
        """
        system = self._build_system(question)
        ontology = load_summary()
        sparql, total_input, total_output, retries = self._generate_with_retry(
            system, question, ontology
        )

        if _is_not_answerable(sparql):
            return PipelineResult(
                sparql=sparql,
                columns=[],
                rows=[],
                provider=self._provider_name,
                model=self._model_name,
                input_tokens=total_input,
                output_tokens=total_output,
                retries=retries,
            )

        result = self._sparql_client.execute(sparql)
        return PipelineResult(
            sparql=sparql,
            columns=result.columns,
            rows=result.rows,
            provider=self._provider_name,
            model=self._model_name,
            input_tokens=total_input,
            output_tokens=total_output,
            retries=retries,
        )

    # ------------------------------------------------------------------
    # Public: streaming path
    # ------------------------------------------------------------------

    async def stream_events(self, question: str) -> AsyncIterator[PipelineEvent]:
        """Run the pipeline and yield typed events as each phase completes.

        Used by `POST /query/stream`. Returns an async generator — the caller
        uses `async for event in pipeline.stream_events(question)` to receive
        events one by one.

        WHAT IS AN ASYNC GENERATOR?
        ----------------------------
        A regular generator function uses `yield` and produces values lazily.
        An async generator also uses `yield` but additionally uses `await` to
        pause without blocking the server. When the server hits an `await`, it
        hands control back to the event loop, which can handle other requests.
        As soon as the awaited operation completes, this function resumes.

        EVENT SEQUENCE (normal success path)
        ─────────────────────────────────────
        TokenEvent × N      (one per token, Phase 1)
        CompleteEvent × 1   (final SPARQL, after Phase 2)
        ResultsEvent  × 1   (GraphDB rows, Phase 3)
        DoneEvent     × 1   (metadata, Phase 4)

        EVENT SEQUENCE (NOT_ANSWERABLE path)
        ─────────────────────────────────────
        TokenEvent × N      (the # NOT_ANSWERABLE: ... comment, token by token)
        CompleteEvent × 1   (the comment as the "sparql")
        DoneEvent     × 1   (metadata, retries=0)
        ← ResultsEvent is NEVER yielded here — GraphDB is never called

        EVENT SEQUENCE (retry path — e.g. 1 retry needed)
        ─────────────────────────────────────────────────
        TokenEvent × N      (initial invalid SPARQL tokens)
        RetryEvent × 1      (attempt=1, error="...")
        CompleteEvent × 1   (the corrected SPARQL)
        ResultsEvent  × 1   (GraphDB rows)
        DoneEvent     × 1   (metadata, retries=1)

        PHASE 1 — Token Streaming (non-blocking)
        -----------------------------------------
        The LLM token stream is a synchronous iterator (the SDK is blocking).
        To avoid freezing the server while waiting for each token, each call
        to `next(iterator)` is run in a background thread via run_in_executor.

        `loop.run_in_executor(None, next, it, _SENTINEL)` means:
          - Take the default thread pool (None = use Python's default pool)
          - In a background thread, call: next(it, _SENTINEL)
          - Return a coroutine that resolves to the result when the thread is done
          - `await` that coroutine — pauses this function, freeing the event loop

        _SENTINEL is a unique Python object created fresh each call. When
        `next(it, _SENTINEL)` returns the sentinel, the iterator is exhausted.
        Using `is _SENTINEL` (identity check, not equality) is safe and fast.

        CRITICAL — read token counts AFTER the loop:
        `stream_result.input_tokens` and `stream_result.output_tokens` start
        at 0 and are populated by the provider's generator closure only after
        the last token is yielded (see StreamResult in base.py). Reading them
        inside the loop would always give 0.

        PHASE 2 — Validate + Retry (synchronous, acceptable at demo scale)
        -------------------------------------------------------------------
        validate_sparql() runs the rdflib parser offline (no network).
        If invalid, a retry prompt is built and provider.generate() is called.
        generate() is a blocking synchronous call — it will hold the event
        loop while waiting for the LLM response. This is acceptable at
        thesis-demo concurrency (typically one user at a time). In a
        production system it would need run_in_executor treatment too.

        The retry template (nl-to-sparql-retry-v1.md) is loaded lazily —
        only on the first validation failure, and cached locally for
        subsequent retries. Its # System section contains {ontology_summary},
        {failed_sparql}, and {error}. The {question} placeholder in the file's
        # User (template) section is NOT extracted by load() and is NOT
        substituted by fill() — the question still travels as the `user`
        argument to provider.generate(retry_system, question).

        Token counts from retry generate() calls are accumulated into
        total_input and total_output, so DoneEvent always reflects the
        true total cost of the full request including retries.

        PHASE 3 — GraphDB Execution (synchronous, blocks event loop)
        -------------------------------------------------------------
        execute() raises RuntimeError on HTTP failure. The error propagates
        up through the async generator and is caught by event_generator() in
        query.py, which emits it as an SSE `error` event.

        Parameters
        ----------
        question : str
            The user's natural-language question (Greek or English).
        """
        # Build the system prompt (same as run()).
        system = self._build_system(question)
        ontology = load_summary()
        logger.info("Starting pipeline with system prompt:\n%s", system)

        # ── Phase 1: stream SPARQL tokens without blocking the event loop ──
        # next() is called in a thread pool so the event loop stays responsive.
        loop = asyncio.get_running_loop()
        stream_result = self._provider.stream(system, question)
        it = stream_result.tokens
        _SENTINEL = object()  # unique object; nothing else will ever `is` this
        full_sparql = ""
        while True:
            token = await loop.run_in_executor(None, next, it, _SENTINEL)
            if token is _SENTINEL:
                break  # iterator exhausted — LLM finished generating
            full_sparql += token
            yield TokenEvent(token=token)

        # Read token counts NOW — after the iterator is fully consumed.
        # These would be 0 if read earlier (deferred population in StreamResult).
        total_input = stream_result.input_tokens
        total_output = stream_result.output_tokens
        full_sparql = _clean_sparql(full_sparql)
        logger.info("\nStreamed SPARQL: %s", full_sparql)

        # ── NOT_ANSWERABLE fast path ──
        # The LLM signals it cannot answer with a special comment. Stop here
        # and never contact GraphDB — there are no results to show.
        if _is_not_answerable(full_sparql):
            yield CompleteEvent(sparql=full_sparql)
            yield DoneEvent(
                provider=self._provider_name,
                model=self._model_name,
                input_tokens=total_input,
                output_tokens=total_output,
                retries=0,
            )
            return  # `return` inside an async generator ends iteration

        # ── Phase 2: validate + retry ──
        retries = 0
        retry_template = None  # loaded lazily on first failure
        error = validate_sparql(full_sparql) or ""
        # `or ""` converts None (valid) to "" so `while error` works cleanly

        while error and retries < _MAX_RETRIES:
            retries += 1
            yield RetryEvent(attempt=retries, error=error)

            # Load the retry template only on the first failure, then reuse.
            if retry_template is None:
                retry_template = load("nl-to-sparql-retry", 1)

            # Build the retry system prompt with the failure details injected.
            # Note: no `question=` kwarg — question goes as the `user` arg below.
            retry_system = fill(
                retry_template,
                ontology_summary=ontology,
                failed_sparql=full_sparql,
                error=error,
            )
            response_obj = self._provider.generate(retry_system, question)
            full_sparql = _clean_sparql(response_obj.text)

            # Accumulate tokens — generate() returns counts immediately (not deferred)
            total_input += response_obj.input_tokens
            total_output += response_obj.output_tokens
            error = validate_sparql(full_sparql) or ""

        logger.info("Final SPARQL after %d retries: %s", retries, full_sparql)

        # CompleteEvent marks the end of SPARQL generation (valid or not).
        # If all retries failed, full_sparql is still invalid — execute() may
        # raise RuntimeError, which propagates as an SSE error event.
        yield CompleteEvent(sparql=full_sparql)

        # ── Phase 3: execute against GraphDB ──
        result = self._sparql_client.execute(full_sparql)
        yield ResultsEvent(columns=result.columns, rows=result.rows)

        # ── Phase 4: done ──
        yield DoneEvent(
            provider=self._provider_name,
            model=self._model_name,
            input_tokens=total_input,
            output_tokens=total_output,
            retries=retries,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _generate_with_retry(
        self, system: str, question: str, ontology: str
    ) -> tuple[str, int, int, int]:
        """Generate SPARQL and retry on validation failure (synchronous path).

        Called only by run(). Mirrors the Phase 2 retry logic of stream_events()
        but also handles the initial generation (no streaming).

        HOW THE LOOP WORKS
        -------------------
        Iterates attempt 0, 1, 2 (range(_MAX_RETRIES + 1) = range(3)):
          - attempt 0: use the main system prompt (already built by run())
          - attempt 1+: build the retry prompt with the previous failure injected

        Returns as soon as a valid SPARQL is produced or NOT_ANSWERABLE is
        detected. If all 3 attempts fail validation, returns the last invalid
        SPARQL anyway — the caller will try to execute it, which may fail at
        GraphDB level (RuntimeError → HTTP 502).

        DIFFERENCE FROM stream_events() RETRY
        ---------------------------------------
        In stream_events(), the initial generation is already done (streaming)
        before the retry loop starts. The loop only handles corrections.
        Here, attempt 0 IS the initial generation — no streaming involved.

        In stream_events(), `retries` counts only corrective attempts (starts
        at 0, increments on each retry). Here, `attempt` is 0-based so a
        successful first attempt returns attempt=0 (meaning 0 retries). Both
        end up reporting the same "number of corrective attempts" in metadata.

        Parameters
        ----------
        system : str
            The pre-built main system prompt from run().
        question : str
            The user's natural-language question.
        ontology : str
            The ontology summary string, passed separately so the retry prompt
            builder can substitute {ontology_summary} without reloading it.

        Returns
        -------
        tuple[str, int, int, int]
            (sparql, total_input_tokens, total_output_tokens, retry_count)
        """
        retry_template = None
        total_input = total_output = 0
        sparql = error = ""

        for attempt in range(_MAX_RETRIES + 1):
            if attempt == 0:
                current_system = system
            else:
                # Build retry prompt only when needed and cache it locally
                if retry_template is None:
                    retry_template = load("nl-to-sparql-retry", 1)
                current_system = fill(
                    retry_template,
                    ontology_summary=ontology,
                    failed_sparql=sparql,
                    error=error,
                )

            response = self._provider.generate(current_system, question)
            total_input += response.input_tokens
            total_output += response.output_tokens
            sparql = _clean_sparql(response.text)

            if _is_not_answerable(sparql):
                # Early exit — not a SPARQL error, just an unanswerable question
                return sparql, total_input, total_output, attempt

            error = validate_sparql(sparql) or ""
            if not error:
                # Valid SPARQL — return immediately with attempt as retry count
                return sparql, total_input, total_output, attempt

            logger.warning("Invalid SPARQL on attempt %d: %s", attempt + 1, error[:120])

        # All attempts exhausted — return the last (still invalid) SPARQL.
        # The caller will try to execute it; GraphDB will likely reject it.
        logger.error("SPARQL still invalid after %d retries: %s", _MAX_RETRIES, error)
        return sparql, total_input, total_output, _MAX_RETRIES


# ---------------------------------------------------------------------------
# Module-level helpers (pure functions — no class state, no side effects)
# ---------------------------------------------------------------------------


def _clean_sparql(text: str) -> str:
    """Strip markdown code fences if the LLM wrapped the query despite instructions.

    The prompt rules explicitly say "output only the SPARQL query — no
    markdown fences", but LLMs sometimes add them anyway. This function
    removes the fences defensively so the pipeline always receives a raw
    SPARQL string.

    Accepts both ` ```sparql ` and plain ` ``` ` as the opening fence,
    case-insensitively. If no fences are present, returns the text unchanged.

    Called after every LLM generation (initial stream and each retry).
    """
    text = text.strip()
    m = re.match(r"^```(?:sparql)?\s*\n?(.*?)\n?```$", text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else text


def _is_not_answerable(text: str) -> bool:
    """Return True if the LLM signalled it cannot answer the question.

    The prompt instructs the model: if the question cannot be answered with
    the EvdoGraph ontology, output exactly `# NOT_ANSWERABLE: <reason>`.

    This function detects that sentinel at the very start of the response
    (after stripping whitespace). It will NOT fire if the comment appears
    inside an otherwise valid SPARQL query.

    Examples
    --------
    "# NOT_ANSWERABLE: question is about weather"  → True
    "# not_answerable: ..."                        → True  (case-insensitive)
    "SELECT ?x WHERE { ... } # NOT_ANSWERABLE"     → False (not at the start)
    "SELECT ?x WHERE { ... }"                      → False
    """
    return bool(re.match(r"^#\s*NOT_ANSWERABLE", text.strip(), re.IGNORECASE))
