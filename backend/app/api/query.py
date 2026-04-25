"""POST /query — synchronous JSON endpoint.
POST /query/stream — SSE streaming endpoint (added in Task 15).

TODO: future — convert to fully async pipeline for higher concurrency.
TODO: future — add auth/rate limiting before any public deployment.
"""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
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


def _generate_with_retry(provider, system: str, question: str, ontology: str):
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
