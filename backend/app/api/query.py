"""POST /query — synchronous JSON endpoint.
POST /query/stream — SSE streaming endpoint (added in Task 15).

TODO: future — convert to fully async pipeline for higher concurrency.
TODO: future — add auth/rate limiting before any public deployment.
"""

from __future__ import annotations

import json
import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.llm.base import LLMProvider
from app.llm.factory import get_provider
from app.ontology.loader import load_summary
from app.prompts.loader import fill, load
from app.sparql.client import SparqlClient, validate_sparql

logger = logging.getLogger(__name__)
router = APIRouter()

_MAX_RETRIES = 2


class QueryRequest(BaseModel):
    """Request body for POST /query."""

    question: str
    provider: str = settings.llm_provider
    model: str = settings.llm_model


class QueryResponse(BaseModel):
    """Response body for POST /query."""

    sparql: str
    columns: list[str]
    rows: list[dict]
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    retries: int


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    """Run the NLQ pipeline: generate SPARQL, validate, execute, return results."""
    provider = get_provider(request.provider, request.model)
    ontology = load_summary()
    system = fill(load("nl-to-sparql", 1), ontology_summary=ontology)

    sparql, total_input, total_output, retries = _generate_with_retry(
        provider, system, request.question, ontology
    )

    client = SparqlClient(settings.graphdb_endpoint)
    try:
        result = client.execute(sparql)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return QueryResponse(
        sparql=sparql,
        columns=result.columns,
        rows=result.rows,
        provider=request.provider,
        model=request.model,
        input_tokens=total_input,
        output_tokens=total_output,
        retries=retries,
    )


def _generate_with_retry(provider: LLMProvider, system: str, question: str, ontology: str):
    """Call the LLM, validate SPARQL output, retry up to _MAX_RETRIES times.

    On each retry the system prompt is replaced with the retry template,
    which includes the failed query and the parse error for context.

    TODO: future — extend LLMProvider to support multi-turn conversation for
    richer retry context (send the original system + failed attempt as history).
    """
    retry_template = None  # loaded lazily on first retry to avoid I/O on happy path
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

        response = provider.generate(current_system, question)
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


def _clean_sparql(text: str) -> str:
    """Strip markdown code fences if the LLM wrapped the query despite being told not to."""
    text = text.strip()
    m = re.match(r"^```(?:sparql)?\s*\n?(.*?)\n?```$", text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else text


def _is_not_answerable(text: str) -> bool:
    """Detect the NOT_ANSWERABLE sentinel defined in the prompt rules."""
    return bool(re.match(r"^#\s*NOT_ANSWERABLE", text.strip()))


@router.post("/query/stream")
async def query_stream(request: QueryRequest) -> EventSourceResponse:
    """SSE streaming endpoint. Emits events:
      sparql_token    — one per LLM output token
      sparql_retry    — when the first attempt fails SPARQL validation
      sparql_complete — the final (validated) SPARQL string
      results         — JSON execution results from GraphDB
      done            — final metadata (provider, model, tokens, retries)
      error           — on any unrecoverable failure

    NOTE: provider.stream() is a sync iterator called inside an async generator.
    This blocks the event loop per token — acceptable at thesis demo concurrency.
    TODO: future — run provider.stream() in a thread pool (asyncio.to_thread).
    TODO: future — revisit transport when building the React frontend:
          browser EventSource only supports GET; use fetch + ReadableStream (POST).
    """

    async def event_generator():
        try:
            provider = get_provider(request.provider, request.model)
            ontology = load_summary()
            system = fill(load("nl-to-sparql", 1), ontology_summary=ontology)

            # Phase 1: stream SPARQL tokens
            full_sparql = ""
            for token in provider.stream(system, request.question):
                full_sparql += token
                yield {"event": "sparql_token", "data": token}

            total_input = getattr(provider, "last_input_tokens", 0)
            total_output = getattr(provider, "last_output_tokens", 0)
            full_sparql = _clean_sparql(full_sparql)

            # Phase 2: validate + retry (non-streaming retries)
            retries = 0
            retry_template = load("nl-to-sparql-retry", 1)
            error = validate_sparql(full_sparql) or ""

            while error and retries < _MAX_RETRIES:
                retries += 1
                yield {
                    "event": "sparql_retry",
                    "data": json.dumps({"attempt": retries, "error": error}),
                }
                retry_system = fill(
                    retry_template,
                    ontology_summary=ontology,
                    failed_sparql=full_sparql,
                    error=error,
                )
                response_obj = provider.generate(retry_system, request.question)
                full_sparql = _clean_sparql(response_obj.text)
                total_input += response_obj.input_tokens
                total_output += response_obj.output_tokens
                error = validate_sparql(full_sparql) or ""

            yield {"event": "sparql_complete", "data": full_sparql}

            # Phase 3: execute against GraphDB
            client = SparqlClient(settings.graphdb_endpoint)
            result = client.execute(full_sparql)
            yield {
                "event": "results",
                "data": json.dumps({"columns": result.columns, "rows": result.rows}),
            }

            # Phase 4: done
            yield {
                "event": "done",
                "data": json.dumps(
                    {
                        "provider": request.provider,
                        "model": request.model,
                        "input_tokens": total_input,
                        "output_tokens": total_output,
                        "retries": retries,
                    }
                ),
            }

        except Exception as exc:
            logger.error("Stream error: %s", exc)
            yield {"event": "error", "data": json.dumps({"message": str(exc)})}

    return EventSourceResponse(event_generator())
