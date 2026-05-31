"""
POST /query       — synchronous JSON endpoint (full pipeline, wait for completion).
POST /query/stream — SSE streaming endpoint (live token-by-token output).

DESIGN PRINCIPLE: THIN ROUTE HANDLERS
--------------------------------------
These route functions are deliberately kept as short as possible. They handle
only HTTP concerns: deserializing the request body, calling the pipeline,
serializing the response, and mapping exceptions to HTTP status codes.

All business logic (prompt construction, LLM calls, SPARQL validation, retry
loop, GraphDB execution) lives exclusively in QueryPipeline (query_pipeline.py).
This separation makes the pipeline independently testable without HTTP.

TODO: add auth/rate limiting before any public deployment.
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
    """Request body accepted by both POST /query and POST /query/stream.

    Fields
    ------
    question : str
        The user's natural-language question (Greek or English). Required —
        no default. FastAPI returns HTTP 422 Unprocessable Entity if missing.
    provider : str
        Which LLM provider to use. Defaults to the value of `LLM_PROVIDER`
        in .env (e.g. "claude"). Can be overridden per request to compare
        providers side-by-side without restarting the server.
    model : str
        Which model within the chosen provider to use. Defaults to
        `LLM_MODEL` in .env (e.g. "claude-haiku-4-5").

    IMPORTANT — defaults are frozen at server startup:
    `settings.llm_provider` and `settings.llm_model` are read from the
    `settings` object once, when Python evaluates this class definition
    (at module import time, i.e. when the server starts). Changing .env
    while the server is running does NOT update these defaults — a restart
    is required. Sending explicit values in the request body always works,
    regardless of server state.
    """

    question: str
    provider: str = settings.llm_provider
    model: str = settings.llm_model


class QueryResponse(BaseModel):
    """Response body for POST /query (the synchronous endpoint).

    All fields map 1-to-1 with PipelineResult — same names, same types.
    The route handler unpacks PipelineResult directly:
        QueryResponse(**result.__dict__)

    If PipelineResult and QueryResponse ever get out of sync (a field renamed
    or added in one but not the other), that unpacking raises a TypeError or
    Pydantic ValidationError at runtime. There is no compile-time check.

    Fields
    ------
    sparql : str
        The final SPARQL query string (or the # NOT_ANSWERABLE: ... comment).
    columns : list[str]
        Variable names from the SELECT clause. Empty on NOT_ANSWERABLE.
    rows : list[dict]
        Result rows from GraphDB. Empty on NOT_ANSWERABLE.
    provider : str
        Which provider was used (echoed back from the request).
    model : str
        Which model was used (echoed back from the request).
    input_tokens : int
        Total prompt tokens consumed across all LLM calls (initial + retries).
    output_tokens : int
        Total generated tokens across all LLM calls. Both token fields are 0
        for cache hits (the cache does not store usage data).
    retries : int
        Number of corrective LLM calls made. 0 means the first attempt
        produced valid SPARQL; max is _MAX_RETRIES (2).
    """

    sparql: str
    columns: list[str]
    rows: list[dict]
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    retries: int


def _make_pipeline(request: QueryRequest) -> QueryPipeline:
    """Construct a fully wired QueryPipeline for a single request.

    This function exists to avoid duplicating the construction logic in both
    the sync and streaming route handlers. It also makes both routes easy to
    test: tests can patch `get_provider` and `SparqlClient` here without
    touching the route functions themselves.

    A fresh QueryPipeline is created for every request — its __init__ only
    stores references (no I/O), so this is free.

    Construction steps:
    1. get_provider(name, model) — factory.py picks the right provider class
       (ClaudeProvider, GeminiProvider, or FakeProvider), constructs it with
       the API key from settings and a fresh DiskCache, and returns it as an
       LLMProvider. Raises ValueError for unknown provider names.
    2. SparqlClient(endpoint) — pointed at settings.graphdb_endpoint. The
       endpoint cannot be overridden per-request (security: callers must not
       redirect the backend to arbitrary SPARQL endpoints).
    3. provider_name and model_name are the raw strings from the request,
       stored for inclusion in DoneEvent / PipelineResult metadata.
    """
    return QueryPipeline(
        provider=get_provider(request.provider, request.model),
        sparql_client=SparqlClient(settings.graphdb_endpoint),
        provider_name=request.provider,
        model_name=request.model,
    )


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    """Run the full NLQ pipeline synchronously and return a JSON result.

    This is a plain synchronous function (no `async`). FastAPI automatically
    runs sync route handlers in a thread pool so the event loop is not blocked.

    REQUEST LIFECYCLE
    -----------------
    1. FastAPI deserializes the JSON body into QueryRequest, applying defaults
       for `provider` and `model` if not provided.
    2. _make_pipeline() constructs the pipeline (provider + SPARQL client).
    3. pipeline.run(question) blocks the thread while it: builds the system
       prompt, calls provider.generate() (LLM HTTP call), validates SPARQL
       with rdflib (offline), retries up to twice if invalid, then calls
       SparqlClient.execute() (GraphDB HTTP call).
    4. On success: PipelineResult is unpacked into QueryResponse. FastAPI
       serializes to JSON → HTTP 200.
    5. On RuntimeError (GraphDB unreachable or rejects the query): converted
       to HTTP 502 Bad Gateway with the error message in the response body.
    6. Other uncaught exceptions (e.g. ValueError from unknown provider name)
       propagate to FastAPI's default handler → HTTP 500.

    ERROR HANDLING NOTE
    -------------------
    Only RuntimeError from SparqlClient.execute() is explicitly caught here.
    An invalid provider name (ValueError from get_provider) will produce
    HTTP 500, not HTTP 400 — this is a known limitation.
    """
    try:
        pipeline = _make_pipeline(request)
        result = pipeline.run(request.question)
    except ValueError as exc:
        # Invalid provider/model combination — bad request from the caller.
        # Surface the validation message (it contains only allowlist info, no internals).
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        # GraphDB or pipeline failure — log full detail, return generic message.
        logger.error("Pipeline error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail="The SPARQL endpoint could not execute the query.",
        )
    return QueryResponse(**result.__dict__)


@router.post("/query/stream")
async def query_stream(request: QueryRequest) -> EventSourceResponse:
    """SSE streaming endpoint — the primary endpoint used by the frontend.

    WHAT IS SSE (Server-Sent Events)?
    -----------------------------------
    SSE is an HTTP protocol where the server keeps the connection open and
    pushes text events to the client over time. The browser reads events as
    they arrive — this is what lets the frontend show the SPARQL query being
    written character by character.

    Each event has a name and a data payload, formatted as:
        event: sparql_token\\r\\n
        data: SELECT\\r\\n
        \\r\\n

    sse_starlette emits \\r\\n line endings. The frontend normalizes them to
    \\n before parsing (documented in backend/CLAUDE.md).

    EVENTS EMITTED (in order)
    --------------------------
    sparql_token    — one per LLM output token (Phase 1)
    sparql_retry    — if SPARQL validation fails and a retry is triggered
    sparql_complete — the final SPARQL string (after all retries)
    results         — JSON execution results from GraphDB
    done            — final metadata (provider, model, tokens, retries)
    error           — on any unrecoverable failure (replaces normal events)

    NOT_ANSWERABLE path (no results event):
        sparql_token × N → sparql_complete → done
        ResultsEvent is NEVER emitted. The frontend must not assume `results`
        always arrives before `done`.

    WHY THIS ENDPOINT ALWAYS RETURNS HTTP 200
    -------------------------------------------
    HTTP status codes are sent in the response header before the body starts
    streaming. Once the server begins an SSE stream, the 200 has already been
    committed — it cannot be changed to 500 if an error occurs later.
    Pipeline errors are therefore communicated in-band as SSE `error` events.
    The client must listen for `error` events, not HTTP status codes, to detect
    streaming failures.

    NOTE: only Phase 1 (token streaming) uses run_in_executor to avoid
    blocking the event loop. Phases 2 (retry generate() calls) and 3
    (SparqlClient.execute()) are blocking synchronous calls inside this async
    generator — acceptable at thesis-demo concurrency (single user).
    """

    async def event_generator():
        """Inner async generator that drives the pipeline and yields SSE dicts.

        Defined as a nested function so it captures `request` from the
        enclosing scope without needing to pass it as an argument.

        The outer try/except catches ANY exception from anywhere inside the
        generator — including inside stream_events() — and converts it to an
        SSE error event. This means even construction failures (e.g. an
        unknown provider name raising ValueError from get_provider) produce
        an SSE error event over HTTP 200, rather than an HTTP 400/500.
        """
        try:
            pipeline = _make_pipeline(request)
            async for event in pipeline.stream_events(request.question):
                yield _event_to_sse(event)
        except Exception as exc:
            # Log the full exception for operator diagnostics; return a generic
            # message to the client so no internal detail is disclosed.
            logger.error("Stream error: %s", exc, exc_info=True)
            yield {"event": "error", "data": json.dumps({"message": "An error occurred while processing your query."})}

    # EventSourceResponse (from sse_starlette) wraps the async generator and
    # handles the SSE wire format. It pulls events from event_generator() on
    # demand and flushes each one to the client immediately.
    return EventSourceResponse(event_generator())


def _event_to_sse(event: PipelineEvent) -> dict:
    """Translate a typed pipeline event into an SSE dict for sse_starlette.

    sse_starlette expects dicts with "event" (the event name) and "data"
    (the payload string). This function is the only place that knows the
    mapping between Python event types and SSE event names.

    DATA FORMAT PER EVENT TYPE
    ---------------------------
    TokenEvent    → data is a raw string (the token text, NOT JSON-encoded)
    RetryEvent    → data is JSON: {"attempt": N, "error": "..."}
    CompleteEvent → data is a raw string (the SPARQL text, NOT JSON-encoded)
    ResultsEvent  → data is JSON: {"columns": [...], "rows": [...]}
    DoneEvent     → data is JSON: {"provider":"...", "model":"...", ...}

    NOTE: TokenEvent and CompleteEvent carry plain strings while the other
    three carry JSON. The frontend must know which events to JSON.parse()
    and which to use as-is — it cannot treat all data fields uniformly.

    THE `raise TypeError` AT THE END
    ---------------------------------
    If stream_events() ever yields an event type not listed in the isinstance
    chain above (e.g. because a new event class was added to query_pipeline.py
    but this function was not updated), Python would fall through all the `if`
    branches and hit this line. The TypeError is then caught by event_generator's
    `except Exception` block and emitted as an SSE error event with a clear
    message like "Unknown pipeline event type: <class '...NewEvent'>".
    Without this guard, the unknown event would be silently skipped or yield
    None, corrupting the SSE stream in a very confusing way.
    """
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
