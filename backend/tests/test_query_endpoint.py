from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.query import router
from app.llm.fake_provider import FakeProvider
from app.sparql.client import SparqlResult


@pytest.fixture
def client():
    from app.api.providers import router as providers_router

    app = FastAPI()
    app.include_router(router)
    app.include_router(providers_router)
    return TestClient(app)


@pytest.fixture
def mock_sparql_result():
    return SparqlResult(columns=["title"], rows=[{"title": "Αλγόριθμοι"}])


def test_post_query_returns_200_with_correct_shape(client, mock_sparql_result):
    with (
        patch("app.api.query.get_provider", return_value=FakeProvider()),
        patch("app.api.query.SparqlClient") as MockClient,
    ):
        MockClient.return_value.execute.return_value = mock_sparql_result

        response = client.post(
            "/query",
            json={"question": "Ποια βιβλία;", "provider": "fake", "model": "fake-v1"},
        )

    assert response.status_code == 200
    body = response.json()
    assert "sparql" in body
    assert "PREFIX evdx:" in body["sparql"]
    assert body["columns"] == ["title"]
    assert body["rows"] == [{"title": "Αλγόριθμοι"}]
    assert body["provider"] == "fake"
    assert body["model"] == "fake-v1"
    assert body["retries"] == 0
    assert body["input_tokens"] >= 0
    assert body["output_tokens"] >= 0


def test_post_query_retries_on_invalid_sparql(client, mock_sparql_result):
    """When the first LLM response is invalid SPARQL, the endpoint retries."""
    bad_sparql = "NOT VALID SPARQL !!!"
    good_sparql = (
        "PREFIX evdx: <https://w3id.org/evdoxus#>\n"
        "SELECT ?t WHERE { ?b a evdx:Book ; evdx:title ?t } LIMIT 5"
    )
    call_count = 0

    def fake_generate(system, user, *, max_tokens=1024):
        nonlocal call_count
        from app.llm.base import LLMResponse

        call_count += 1
        return LLMResponse(
            text=bad_sparql if call_count == 1 else good_sparql,
            input_tokens=10,
            output_tokens=5,
        )

    fake = FakeProvider()
    fake.generate = fake_generate

    with (
        patch("app.api.query.get_provider", return_value=fake),
        patch("app.api.query.SparqlClient") as MockClient,
    ):
        MockClient.return_value.execute.return_value = mock_sparql_result

        response = client.post(
            "/query",
            json={"question": "test", "provider": "fake", "model": "fake-v1"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["retries"] == 1
    assert body["sparql"] == good_sparql


def test_post_query_returns_502_on_sparql_execution_failure(client):
    with (
        patch("app.api.query.get_provider", return_value=FakeProvider()),
        patch("app.api.query.SparqlClient") as MockClient,
    ):
        MockClient.return_value.execute.side_effect = RuntimeError("timeout")

        response = client.post(
            "/query",
            json={"question": "test", "provider": "fake", "model": "fake-v1"},
        )

    assert response.status_code == 502


def test_get_providers_returns_list(client):
    response = client.get("/providers")
    assert response.status_code == 200
    body = response.json()
    assert "providers" in body
    ids = [p["id"] for p in body["providers"]]
    assert "claude" in ids
    assert "gemini" in ids
    assert "fake" in ids
    for p in body["providers"]:
        assert len(p["models"]) > 0


def test_post_query_stream_yields_sse_events(client, mock_sparql_result):
    """The streaming endpoint must emit sparql_token, sparql_complete, results, and done events."""
    with (
        patch("app.api.query.get_provider", return_value=FakeProvider()),
        patch("app.api.query.SparqlClient") as MockClient,
    ):
        MockClient.return_value.execute.return_value = mock_sparql_result

        with client.stream(
            "POST",
            "/query/stream",
            json={"question": "Ποια βιβλία;", "provider": "fake", "model": "fake-v1"},
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            raw = response.read().decode()

    assert "event: sparql_token" in raw
    assert "event: sparql_complete" in raw
    assert "event: results" in raw
    assert "event: done" in raw


# --- H-1: model allowlist tests ---

def test_post_query_returns_400_for_invalid_model(client):
    """Requesting an unlisted model must return HTTP 400, not 500."""
    response = client.post(
        "/query",
        json={"question": "test", "provider": "claude", "model": "claude-opus-99"},
    )
    assert response.status_code == 400
    assert "not permitted" in response.json()["detail"]


# --- H-2: error message sanitization tests ---

def test_post_query_502_does_not_leak_internal_detail(client):
    """The 502 response body must not contain the internal error string."""
    with (
        patch("app.api.query.get_provider", return_value=FakeProvider()),
        patch("app.api.query.SparqlClient") as MockClient,
    ):
        MockClient.return_value.execute.side_effect = RuntimeError(
            "Connection refused: secret.internal.host:7200"
        )
        response = client.post(
            "/query",
            json={"question": "test", "provider": "fake", "model": "fake-v1"},
        )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "secret.internal.host" not in detail
    assert "7200" not in detail
    assert "SPARQL endpoint" in detail


def test_post_query_stream_error_does_not_leak_internal_detail(client, mock_sparql_result):
    """The SSE error event must not contain internal exception details."""
    with (
        patch("app.api.query.get_provider", return_value=FakeProvider()),
        patch("app.api.query.SparqlClient") as MockClient,
    ):
        MockClient.return_value.execute.side_effect = RuntimeError(
            "hostname=db.private.lan port=7200 auth=admin"
        )
        with client.stream(
            "POST",
            "/query/stream",
            json={"question": "test", "provider": "fake", "model": "fake-v1"},
        ) as response:
            raw = response.read().decode()

    assert "event: error" in raw
    assert "db.private.lan" not in raw
    assert "auth=admin" not in raw


# --- /sparql/execute endpoint tests ---

def test_execute_raw_sparql_returns_200_with_columns_and_rows(client):
    """A valid SPARQL query is validated, executed, and returns columns/rows."""
    valid_sparql = (
        "PREFIX evdx: <https://w3id.org/evdoxus#>\n"
        "SELECT ?title WHERE { ?b a evdx:Book ; evdx:title ?title } LIMIT 5"
    )
    with patch("app.api.query.SparqlClient") as MockClient:
        MockClient.return_value.execute.return_value = SparqlResult(
            columns=["title"],
            rows=[{"title": "Αλγόριθμοι"}, {"title": "Γραφήματα"}],
        )
        response = client.post("/sparql/execute", json={"sparql": valid_sparql})

    assert response.status_code == 200
    body = response.json()
    assert body["columns"] == ["title"]
    assert len(body["rows"]) == 2
    assert body["rows"][0]["title"] == "Αλγόριθμοι"
    # The LLM is bypassed entirely — SparqlClient was called with the raw query
    MockClient.return_value.execute.assert_called_once_with(valid_sparql)


def test_execute_raw_sparql_returns_400_for_invalid_syntax(client):
    """Syntactically invalid SPARQL must return 400; GraphDB must never be called."""
    with patch("app.api.query.SparqlClient") as MockClient:
        response = client.post("/sparql/execute", json={"sparql": "SELECT WHERE"})

    assert response.status_code == 400
    # The validation error message must be present but the internal GraphDB client
    # must never have been called — no point executing if the syntax is broken.
    assert response.json()["detail"]  # some parse-error text from rdflib
    MockClient.return_value.execute.assert_not_called()


def test_execute_raw_sparql_returns_502_on_execution_failure(client):
    """A GraphDB error must produce HTTP 502 with a generic message (no internal detail)."""
    valid_sparql = (
        "PREFIX evdx: <https://w3id.org/evdoxus#>\n"
        "SELECT ?title WHERE { ?b a evdx:Book ; evdx:title ?title } LIMIT 1"
    )
    with patch("app.api.query.SparqlClient") as MockClient:
        MockClient.return_value.execute.side_effect = RuntimeError(
            "Connection refused: secret.internal.host:7200"
        )
        response = client.post("/sparql/execute", json={"sparql": valid_sparql})

    assert response.status_code == 502
    detail = response.json()["detail"]
    # Generic message must be returned — the raw exception must never be forwarded.
    assert "secret.internal.host" not in detail
    assert "SPARQL endpoint" in detail


def test_post_query_stream_not_answerable_skips_execution(client):
    """NOT_ANSWERABLE sentinel must short-circuit — no GraphDB call, no error event."""
    not_answerable_response = "# NOT_ANSWERABLE: question is out of scope"

    from app.llm.base import LLMResponse, StreamResult

    class NotAnswerableProvider:
        def generate(self, system, user, *, max_tokens=1024):
            return LLMResponse(text=not_answerable_response, input_tokens=5, output_tokens=3)

        def stream(self, system, user, *, max_tokens=1024):
            return StreamResult(tokens=iter([not_answerable_response]), input_tokens=5, output_tokens=3)

    with (
        patch("app.api.query.get_provider", return_value=NotAnswerableProvider()),
        patch("app.api.query.SparqlClient") as MockClient,
    ):
        with client.stream("POST", "/query/stream", json={
            "question": "Ποιος είναι ο καλύτερος παίκτης;",
            "provider": "fake",
            "model": "fake-v1",
        }) as response:
            raw = response.read().decode()

    # Must have sparql_complete and done, must NOT have error or results
    assert "event: sparql_complete" in raw
    assert "event: done" in raw
    assert "event: error" not in raw
    MockClient.return_value.execute.assert_not_called()
