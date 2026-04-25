from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.query import router, QueryRequest, QueryResponse
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

        with client.stream("POST", "/query/stream", json={
            "question": "Ποια βιβλία;", "provider": "fake", "model": "fake-v1"
        }) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            raw = response.read().decode()

    assert "event: sparql_token" in raw
    assert "event: sparql_complete" in raw
    assert "event: results" in raw
    assert "event: done" in raw
