"""Tests for QueryPipeline — exercise business logic without HTTP."""

from unittest.mock import MagicMock

from app.llm.base import LLMResponse, StreamResult
from app.llm.fake_provider import FakeProvider
from app.pipeline.query_pipeline import (
    CompleteEvent,
    DoneEvent,
    QueryPipeline,
    ResultsEvent,
    RetryEvent,
    TokenEvent,
)
from app.sparql.client import SparqlClient, SparqlResult


def _make_pipeline(provider=None, sparql_result=None):
    mock_client = MagicMock(spec=SparqlClient)
    mock_client.execute.return_value = sparql_result or SparqlResult(
        columns=["title"], rows=[{"title": "Αλγόριθμοι"}]
    )
    return QueryPipeline(
        provider=provider or FakeProvider(),
        sparql_client=mock_client,
        provider_name="fake",
        model_name="fake-v1",
    ), mock_client


def test_run_returns_pipeline_result():
    pipeline, _ = _make_pipeline()
    result = pipeline.run("ποια βιβλία;")
    assert "PREFIX" in result.sparql
    assert result.columns == ["title"]
    assert result.rows == [{"title": "Αλγόριθμοι"}]
    assert result.provider == "fake"
    assert result.model == "fake-v1"
    assert result.retries == 0
    assert result.input_tokens >= 0
    assert result.output_tokens >= 0


def test_run_raises_passes_through_sparql_client_error():
    mock_client = MagicMock(spec=SparqlClient)
    mock_client.execute.side_effect = RuntimeError("timeout")
    pipeline = QueryPipeline(FakeProvider(), mock_client, "fake", "fake-v1")
    try:
        pipeline.run("test")
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "timeout" in str(exc)


async def test_stream_events_yields_expected_event_types():
    pipeline, _ = _make_pipeline()
    events = [e async for e in pipeline.stream_events("ποια βιβλία;")]
    types = [type(e) for e in events]
    assert TokenEvent in types
    assert CompleteEvent in types
    assert ResultsEvent in types
    assert DoneEvent in types


async def test_stream_events_token_events_assemble_to_sparql():
    pipeline, _ = _make_pipeline()
    events = [e async for e in pipeline.stream_events("test")]
    tokens = "".join(e.token for e in events if isinstance(e, TokenEvent))
    complete = next(e for e in events if isinstance(e, CompleteEvent))
    assert tokens.strip() == complete.sparql.strip()


async def test_stream_events_not_answerable_skips_execution():
    """NOT_ANSWERABLE must short-circuit without calling SparqlClient.execute."""
    not_answerable = "# NOT_ANSWERABLE: question is out of scope"

    class NotAnswerableProvider:
        def generate(self, system, user, *, max_tokens=1024):
            return LLMResponse(text=not_answerable, input_tokens=5, output_tokens=3)

        def stream(self, system, user, *, max_tokens=1024):
            return StreamResult(tokens=iter([not_answerable]), input_tokens=5, output_tokens=3)

    pipeline, mock_client = _make_pipeline(provider=NotAnswerableProvider())
    events = [e async for e in pipeline.stream_events("test")]
    mock_client.execute.assert_not_called()
    types = [type(e) for e in events]
    assert CompleteEvent in types
    assert DoneEvent in types
    assert ResultsEvent not in types


async def test_stream_events_retry_on_invalid_sparql():
    """A provider returning invalid SPARQL on first attempt must emit RetryEvent."""
    bad_sparql = "NOT VALID SPARQL !!!"
    good_sparql = (
        "PREFIX evdx: <https://w3id.org/evdoxus#>\n"
        "SELECT ?t WHERE { ?b a evdx:Book ; evdx:title ?t } LIMIT 5"
    )

    class RetryProvider:
        def generate(self, system, user, *, max_tokens=1024):
            # Phase 2 retry: first generate() call returns good SPARQL
            return LLMResponse(text=good_sparql, input_tokens=10, output_tokens=5)

        def stream(self, system, user, *, max_tokens=1024):
            # Phase 1: stream returns invalid SPARQL, triggering Phase 2 retry
            return StreamResult(tokens=iter([bad_sparql]), input_tokens=10, output_tokens=5)

    pipeline, _ = _make_pipeline(provider=RetryProvider())
    events = [e async for e in pipeline.stream_events("test")]
    retry_events = [e for e in events if isinstance(e, RetryEvent)]
    assert len(retry_events) == 1
    assert retry_events[0].attempt == 1


async def test_done_event_carries_correct_metadata():
    pipeline, _ = _make_pipeline()
    events = [e async for e in pipeline.stream_events("test")]
    done = next(e for e in events if isinstance(e, DoneEvent))
    assert done.provider == "fake"
    assert done.model == "fake-v1"
    assert done.retries == 0
