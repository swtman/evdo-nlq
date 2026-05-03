"""QueryPipeline — orchestrates NL → SPARQL (with retry) → GraphDB execution.

This module owns all business logic for the NLQ pipeline so that API route
handlers stay thin transport wrappers.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.llm.base import LLMProvider
from app.ontology.loader import load_summary
from app.prompts.loader import fill, load
from app.sparql.client import SparqlClient, validate_sparql

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2


# ---------------------------------------------------------------------------
# Typed event objects — the streaming path yields these; the route handler
# maps them to SSE dicts. No SSE concerns live inside this module.
# ---------------------------------------------------------------------------


@dataclass
class TokenEvent:
    """A single text token streamed from the LLM."""

    token: str


@dataclass
class RetryEvent:
    """Emitted when a SPARQL validation failure triggers a retry."""

    attempt: int
    error: str


@dataclass
class CompleteEvent:
    """The final (post-retry) validated SPARQL query."""

    sparql: str


@dataclass
class ResultsEvent:
    """GraphDB execution results."""

    columns: list[str]
    rows: list[dict]


@dataclass
class DoneEvent:
    """Final metadata emitted after all pipeline phases complete."""

    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    retries: int


PipelineEvent = TokenEvent | RetryEvent | CompleteEvent | ResultsEvent | DoneEvent


# ---------------------------------------------------------------------------
# Result type for the synchronous path
# ---------------------------------------------------------------------------


@dataclass
class PipelineResult:
    """Structured result from the synchronous pipeline run."""

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
    """Orchestrates: NL → SPARQL generation (with retry) → GraphDB execution.

    Construct once per request with the chosen LLM provider and SPARQL client.
    """

    def __init__(
        self,
        provider: LLMProvider,
        sparql_client: SparqlClient,
        provider_name: str,
        model_name: str,
    ) -> None:
        self._provider = provider
        self._sparql_client = sparql_client
        self._provider_name = provider_name
        self._model_name = model_name

    def run(self, question: str) -> PipelineResult:
        """Synchronous pipeline: generate SPARQL, validate/retry, execute, return result."""
        ontology = load_summary()
        system = fill(load("nl-to-sparql", 1), ontology_summary=ontology)
        sparql, total_input, total_output, retries = self._generate_with_retry(
            system, question, ontology
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

    async def stream_events(self, question: str) -> AsyncIterator[PipelineEvent]:
        """Streaming pipeline: yields typed events through all 4 phases.

        Phase 1 — token streaming via run_in_executor (non-blocking per token).
        Phase 2 — validate + retry (sync generate() calls; fine at demo concurrency).
        Phase 3 — GraphDB execution.
        Phase 4 — done metadata.
        """
        ontology = load_summary()
        system = fill(load("nl-to-sparql", 1), ontology_summary=ontology)

        # Phase 1: stream SPARQL tokens without blocking the event loop.
        # next() is called in a thread pool so the event loop stays responsive.
        loop = asyncio.get_running_loop()
        stream_result = self._provider.stream(system, question)
        it = stream_result.tokens
        _SENTINEL = object()
        full_sparql = ""
        while True:
            token = await loop.run_in_executor(None, next, it, _SENTINEL)
            if token is _SENTINEL:
                break
            full_sparql += token
            yield TokenEvent(token=token)

        total_input = stream_result.input_tokens
        total_output = stream_result.output_tokens
        full_sparql = _clean_sparql(full_sparql)
        logger.info("Streamed SPARQL: %s", full_sparql)

        if _is_not_answerable(full_sparql):
            yield CompleteEvent(sparql=full_sparql)
            yield DoneEvent(
                provider=self._provider_name,
                model=self._model_name,
                input_tokens=total_input,
                output_tokens=total_output,
                retries=0,
            )
            return

        # Phase 2: validate + retry (non-streaming)
        retries = 0
        retry_template = None
        error = validate_sparql(full_sparql) or ""

        while error and retries < _MAX_RETRIES:
            retries += 1
            yield RetryEvent(attempt=retries, error=error)
            if retry_template is None:
                retry_template = load("nl-to-sparql-retry", 1)
            retry_system = fill(
                retry_template,
                ontology_summary=ontology,
                failed_sparql=full_sparql,
                error=error,
            )
            response_obj = self._provider.generate(retry_system, question)
            full_sparql = _clean_sparql(response_obj.text)
            total_input += response_obj.input_tokens
            total_output += response_obj.output_tokens
            error = validate_sparql(full_sparql) or ""

        logger.info("Final SPARQL after %d retries: %s", retries, full_sparql)
        yield CompleteEvent(sparql=full_sparql)

        # Phase 3: execute against GraphDB
        result = self._sparql_client.execute(full_sparql)
        yield ResultsEvent(columns=result.columns, rows=result.rows)

        # Phase 4: done
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
        """Call provider.generate, validate SPARQL, retry up to _MAX_RETRIES times.

        Returns (sparql, total_input_tokens, total_output_tokens, retry_count).
        """
        retry_template = None
        total_input = total_output = 0
        sparql = error = ""

        for attempt in range(_MAX_RETRIES + 1):
            if attempt == 0:
                current_system = system
            else:
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
                return sparql, total_input, total_output, attempt

            error = validate_sparql(sparql) or ""
            if not error:
                return sparql, total_input, total_output, attempt

            logger.warning("Invalid SPARQL on attempt %d: %s", attempt + 1, error[:120])

        logger.error("SPARQL still invalid after %d retries: %s", _MAX_RETRIES, error)
        return sparql, total_input, total_output, _MAX_RETRIES


# ---------------------------------------------------------------------------
# Module-level helpers (no state)
# ---------------------------------------------------------------------------


def _clean_sparql(text: str) -> str:
    """Strip markdown code fences if the LLM wrapped the query despite instructions."""
    text = text.strip()
    m = re.match(r"^```(?:sparql)?\s*\n?(.*?)\n?```$", text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else text


def _is_not_answerable(text: str) -> bool:
    """Detect the NOT_ANSWERABLE sentinel defined in the prompt rules."""
    return bool(re.match(r"^#\s*NOT_ANSWERABLE", text.strip()))
