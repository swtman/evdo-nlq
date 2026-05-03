"""POST /query — synchronous JSON endpoint.
POST /query/stream — SSE streaming endpoint.

Route handlers are thin transport wrappers. All business logic lives in
app.pipeline.query_pipeline.QueryPipeline.

TODO: future — add auth/rate limiting before any public deployment.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.llm.factory import get_provider
from app.pipeline.query_pipeline import (
    CompleteEvent,
    DoneEvent,
    PipelineEvent,
    QueryPipeline,
    ResultsEvent,
    RetryEvent,
    TokenEvent,
)
from app.sparql.client import SparqlClient

logger = logging.getLogger(__name__)
router = APIRouter()


class QueryRequest(BaseModel):
    """Request body for POST /query and POST /query/stream."""

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


def _make_pipeline(request: QueryRequest) -> QueryPipeline:
    """Construct a QueryPipeline for one request."""
    return QueryPipeline(
        provider=get_provider(request.provider, request.model),
        sparql_client=SparqlClient(settings.graphdb_endpoint),
        provider_name=request.provider,
        model_name=request.model,
    )


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    """Run the full NLQ pipeline synchronously and return a JSON result."""
    pipeline = _make_pipeline(request)
    try:
        result = pipeline.run(request.question)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return QueryResponse(**result.__dict__)


@router.post("/query/stream")
async def query_stream(request: QueryRequest) -> EventSourceResponse:
    """SSE streaming endpoint. Emits events:
      sparql_token    — one per LLM output token
      sparql_retry    — when SPARQL validation fails and a retry is triggered
      sparql_complete — the final validated SPARQL string
      results         — JSON execution results from GraphDB
      done            — final metadata (provider, model, tokens, retries)
      error           — on any unrecoverable failure

    NOTE: stream_events() is a sync iterator called inside an async generator,
    blocking the event loop per token. Fixed by AP3 (asyncio.run_in_executor).
    """

    async def event_generator():
        try:
            pipeline = _make_pipeline(request)
            async for event in pipeline.stream_events(request.question):
                yield _event_to_sse(event)
        except Exception as exc:
            logger.error("Stream error: %s", exc)
            yield {"event": "error", "data": json.dumps({"message": str(exc)})}

    return EventSourceResponse(event_generator())


def _event_to_sse(event: PipelineEvent) -> dict:
    """Map a typed pipeline event to an SSE dict understood by sse_starlette."""
    if isinstance(event, TokenEvent):
        return {"event": "sparql_token", "data": event.token}
    if isinstance(event, RetryEvent):
        return {"event": "sparql_retry", "data": json.dumps({"attempt": event.attempt, "error": event.error})}
    if isinstance(event, CompleteEvent):
        return {"event": "sparql_complete", "data": event.sparql}
    if isinstance(event, ResultsEvent):
        return {"event": "results", "data": json.dumps({"columns": event.columns, "rows": event.rows})}
    if isinstance(event, DoneEvent):
        return {
            "event": "done",
            "data": json.dumps({
                "provider": event.provider,
                "model": event.model,
                "input_tokens": event.input_tokens,
                "output_tokens": event.output_tokens,
                "retries": event.retries,
            }),
        }
    raise TypeError(f"Unknown pipeline event type: {type(event)}")
