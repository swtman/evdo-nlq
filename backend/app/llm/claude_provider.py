"""
Claude (Anthropic) implementation of LLMProvider.

BOUNDARY RULE
-------------
Only this file may import the `anthropic` package. Every other module must
interact with LLMs through the `LLMProvider` Protocol defined in `base.py`.
This keeps Claude-specific code in one place — if Anthropic changes their SDK,
only this file needs to change.
"""

from __future__ import annotations

import logging
from typing import Iterator

import anthropic  # the official Anthropic Python SDK

from app.llm.base import LLMResponse, StreamResult
from app.llm.cache import DiskCache

logger = logging.getLogger(__name__)


class ClaudeProvider:
    """Talks to the Anthropic Claude API and wraps every call with a disk cache.

    HOW IT IS CONSTRUCTED
    ---------------------
    ClaudeProvider is never instantiated directly in route or pipeline code.
    The factory (`app/llm/factory.py`) creates it once per request, injecting
    the model name, API key, and a DiskCache instance. The pipeline then calls
    `generate()` or `stream()` without knowing anything about Claude internals.

    WHAT THE ANTHROPIC CLIENT IS
    ----------------------------
    `anthropic.Anthropic(api_key=...)` creates an HTTP client that knows how
    to talk to Anthropic's servers. Think of it like opening a connection to
    a web service — you create it once and reuse it for all calls.
    """

    def __init__(self, model: str, api_key: str, cache: DiskCache) -> None:
        """Store the model name, create the Anthropic client, and attach the cache.

        Parameters
        ----------
        model : str
            The Claude model identifier, e.g. "claude-haiku-4-5". Passed to
            every API call so the right model is used.
        api_key : str
            The Anthropic secret key from `.env`. Passed to the SDK client so
            it can authenticate with Anthropic's servers.
        cache : DiskCache
            The shared disk cache. Checked before every API call; written to
            after every successful API call.
        """
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key)
        self._cache = cache

    # ------------------------------------------------------------------
    # generate() — non-streaming path
    # ------------------------------------------------------------------

    def generate(self, system: str, user: str, *, max_tokens: int = 1024) -> LLMResponse:
        """Ask Claude for a complete answer and wait for it to finish.

        Used by:
        - The synchronous `/query` endpoint.
        - The retry loop in the streaming pipeline (after the first attempt
          fails SPARQL validation, retries switch to non-streaming for
          simplicity).

        FLOW
        ----
        1. Check the disk cache — if we have seen this exact prompt + model
           before, return the saved response immediately (0 API cost).
        2. If not cached: send the prompt to Claude, wait for the full reply.
        3. Save the reply to cache for next time.
        4. Log token usage so you can spot prompt bloat early.
        5. Return an LLMResponse with the text and token counts.

        Parameters
        ----------
        system : str
            The system prompt — background instructions for the LLM (ontology
            summary + NL-to-SPARQL prompt template).
        user : str
            The user's natural-language question.
        max_tokens : int
            Hard cap on how long Claude's answer can be. Keyword-only.

        Returns
        -------
        LLMResponse
            On a cache hit: `input_tokens` and `output_tokens` are both 0
            (usage is unknown for cached responses — this is intentional).
            On a real API call: token counts reflect actual usage.
        """
        # Step 1 — cache check
        cached = self._cache.get(system, user, self._model)
        if cached is not None:
            return LLMResponse(text=cached, input_tokens=0, output_tokens=0)

        # Step 2 — call the Anthropic API (non-streaming)
        # `messages.create` sends the prompt and blocks until Claude finishes.
        # The `messages` list follows the chat format: alternating user/
        # assistant turns. Here we always send exactly one user message.
        message = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )

        # The response body (`message.content`) is a list of "content blocks".
        # In normal text responses there is always exactly one block of type
        # TextBlock that has a `.text` attribute. The guard below protects
        # against unexpected block types (e.g. tool_use) that could appear if
        # the API behaviour changes.
        block = message.content[0]
        if not hasattr(block, "text"):
            raise RuntimeError(f"Unexpected content block type from Claude: {type(block).__name__}")
        text = block.text

        # Step 3 — save to cache
        self._cache.set(system, user, self._model, text)

        # Step 4 — log usage (input/output token counts)
        logger.info(
            "Claude [%s] input=%d output=%d",
            self._model,
            message.usage.input_tokens,
            message.usage.output_tokens,
        )

        # Step 5 — return
        return LLMResponse(
            text=text,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )

    # ------------------------------------------------------------------
    # stream() — streaming path
    # ------------------------------------------------------------------

    def stream(self, system: str, user: str, *, max_tokens: int = 1024) -> StreamResult:
        """Ask Claude for an answer delivered token-by-token.

        Used only for the initial SPARQL generation in the `/query/stream`
        endpoint, so the user can watch the query appear in real time.

        THE DEFERRED-POPULATION PATTERN — the most important thing here
        ---------------------------------------------------------------
        We need to return a StreamResult *immediately* (before Claude has even
        started responding), but we also need to fill in `input_tokens` and
        `output_tokens` — which are only known *after* Claude finishes.

        The solution is a closure (see below). In short:

          1. Create a StreamResult with empty token iterator and usage = 0.
          2. Define a generator function `_gen()` that will run lazily — it
             only executes when the caller starts iterating over the tokens.
          3. At the end of `_gen()`, when the stream is fully consumed, mutate
             the StreamResult's usage fields in place.
          4. Assign `_gen()` as the token iterator and return the StreamResult.

        The caller (pipeline) receives the StreamResult, iterates `tokens`
        until exhausted, then reads `input_tokens` / `output_tokens` — which
        by that point have been populated by `_gen()`.

        WHAT IS A GENERATOR / CLOSURE?
        --------------------------------
        A *generator* is a function that uses `yield` instead of `return`. It
        does not run immediately — it produces values one at a time, on demand,
        each time the caller asks for the next one.

        A *closure* is an inner function that "remembers" variables from the
        outer function even after the outer function has returned. Here, `_gen`
        is a closure that remembers `result` (the StreamResult object), `system`,
        `user`, and `self` — even though `stream()` has already returned.

        When `_gen()` finishes, it writes into `result.input_tokens` and
        `result.output_tokens`. Because `result` is the *same object* the
        caller is holding, the caller sees the updated values.

        FLOW
        ----
        1. Create an empty StreamResult (tokens = empty iterator, usage = 0).
        2. Define `_gen()` — a generator that:
             a. Checks the cache. On a hit: yields the full cached text as one
                chunk and returns (no token-by-token, it's already all there).
             b. On a miss: opens a live streaming connection to Claude,
                yields each token as it arrives, accumulates the full text.
             c. After the last token: saves to cache, reads final usage, and
                mutates `result.input_tokens` / `result.output_tokens`.
        3. Assign `_gen()` as the token iterator.
        4. Return the StreamResult.
        """
        # Step 1 — create the StreamResult with a placeholder empty iterator.
        # `iter([])` is an iterator over an empty list — it yields nothing.
        # It will be replaced by the real generator on the last line of stream().
        result = StreamResult(tokens=iter([]))

        # Step 2 — define the generator closure.
        def _gen() -> Iterator[str]:
            # 2a — cache check
            cached = self._cache.get(system, user, self._model)
            if cached is not None:
                # Yield the entire cached string as one chunk and stop.
                # No usage data is available for cached responses.
                yield cached
                return  # `return` inside a generator just stops iteration

            # 2b — live streaming from Claude
            full_text = ""
            # `with ... as s` is a context manager — it opens the stream and
            # ensures it is cleanly closed when the block exits, even on error.
            with self._client.messages.stream(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            ) as s:
                for token in s.text_stream:   # each token is a small string chunk
                    full_text += token        # accumulate for cache write
                    yield token               # forward to the pipeline immediately

            # 2c — stream is now fully consumed
            self._cache.set(system, user, self._model, full_text)

            # `get_final_message()` is an Anthropic SDK method that returns the
            # completed message object (including usage) after streaming ends.
            usage = s.get_final_message().usage

            # Mutate the StreamResult that the caller is already holding.
            # This is the deferred-population step described above.
            result.input_tokens = usage.input_tokens
            result.output_tokens = usage.output_tokens

            logger.info(
                "Claude stream [%s] input=%d output=%d",
                self._model,
                result.input_tokens,
                result.output_tokens,
            )

        # Step 3 — replace the placeholder with the real generator.
        # Calling `_gen()` does NOT run it — it just creates the generator
        # object. The pipeline starts the actual execution when it first
        # calls `next()` on `result.tokens`.
        result.tokens = _gen()

        # Step 4 — return immediately. The pipeline will drive _gen() by
        # iterating result.tokens in its own loop.
        return result
