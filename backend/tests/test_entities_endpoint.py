"""Tests for GET /entities/search (app.api.entities).

This endpoint had zero test coverage before book search was added — worth
fixing now since its behavior is changing (the class=book stub is gone).
``rank_titles`` is monkeypatched throughout so these tests never touch
``entities.db``.

Run from backend/:
    uv run pytest tests/test_entities_endpoint.py -v
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.entities import router
from app.grounding.title_index import TitleMatch


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_course_search_defaults_and_returns_results(client):
    with patch("app.api.entities.rank_titles") as mock_rank:
        mock_rank.return_value = [
            TitleMatch(normalized_title="x", score=1.0, surface_forms=["X"], entity_class="course")
        ]
        response = client.get("/entities/search", params={"q": "X"})

    assert response.status_code == 200
    # class= was omitted -> defaults to "course".
    mock_rank.assert_called_once_with("X", k=50, entity_class="course")
    body = response.json()
    assert body["total"] == 1
    assert body["results"][0]["title"] == "X"


def test_book_search_reaches_ranker_with_book_class(client):
    """The former stub (class=book always returning []) is gone — this is
    the assertion that actually pins that."""
    with patch("app.api.entities.rank_titles") as mock_rank:
        mock_rank.return_value = [
            TitleMatch(normalized_title="βασεισ δεδομενων", score=0.9,
                       surface_forms=["Βάσεις Δεδομένων"], entity_class="book")
        ]
        response = client.get("/entities/search", params={"q": "βασεις", "class": "book"})

    assert response.status_code == 200
    mock_rank.assert_called_once_with("βασεις", k=50, entity_class="book")
    body = response.json()
    assert body["total"] == 1
    assert body["results"][0]["title"] == "Βάσεις Δεδομένων"


def test_unknown_class_returns_400(client):
    response = client.get("/entities/search", params={"q": "x", "class": "publisher"})

    assert response.status_code == 400
    assert "publisher" in response.json()["detail"]
    assert "course" in response.json()["detail"]
    assert "book" in response.json()["detail"]


def test_limit_is_passed_through_as_k(client):
    with patch("app.api.entities.rank_titles") as mock_rank:
        mock_rank.return_value = []
        client.get("/entities/search", params={"q": "x", "limit": 10})

    mock_rank.assert_called_once_with("x", k=10, entity_class="course")


def test_limit_out_of_bounds_rejected(client):
    assert client.get("/entities/search", params={"q": "x", "limit": 0}).status_code == 422
    assert client.get("/entities/search", params={"q": "x", "limit": 101}).status_code == 422


def test_empty_query_rejected(client):
    response = client.get("/entities/search", params={"q": ""})
    assert response.status_code == 422


def test_no_results_returns_empty_list_not_error(client):
    with patch("app.api.entities.rank_titles") as mock_rank:
        mock_rank.return_value = []
        response = client.get("/entities/search", params={"q": "asdfasdf", "class": "book"})

    assert response.status_code == 200
    body = response.json()
    assert body["results"] == []
    assert body["total"] == 0


# ---------------------------------------------------------------------------
# _pick_display_surface — mixed-case preference + display-only whitespace
# collapse (the raw literal stays untouched in the database / grounding path,
# see app/grounding/clean.py; this is purely a search-UI presentation choice)
# ---------------------------------------------------------------------------


def test_display_prefers_mixed_case_over_all_caps(client):
    with patch("app.api.entities.rank_titles") as mock_rank:
        mock_rank.return_value = [
            TitleMatch(
                normalized_title="x",
                score=1.0,
                surface_forms=["ΑΡΧΙΤΕΚΤΟΝΙΚΗ ΥΠΟΛΟΓΙΣΤΩΝ", "Αρχιτεκτονική Υπολογιστών"],
            )
        ]
        response = client.get("/entities/search", params={"q": "x"})

    assert response.json()["results"][0]["title"] == "Αρχιτεκτονική Υπολογιστών"


def test_display_falls_back_to_first_when_all_uppercase(client):
    with patch("app.api.entities.rank_titles") as mock_rank:
        mock_rank.return_value = [
            TitleMatch(normalized_title="x", score=1.0, surface_forms=["ΒΑΣΕΙΣ ΔΕΔΟΜΕΝΩΝ"])
        ]
        response = client.get("/entities/search", params={"q": "x"})

    assert response.json()["results"][0]["title"] == "ΒΑΣΕΙΣ ΔΕΔΟΜΕΝΩΝ"


def test_display_collapses_whitespace_but_matching_stays_on_raw_data(client):
    """The raw KG literal ('ΟΙΚΟΝΟΜΕΤΡΙΑ\\xa0 ΙΙ', with an embedded NBSP) is
    what search matched against (that's clean.py's job, tested separately) —
    this endpoint's only responsibility is not showing the raw invisible
    character to the user."""
    with patch("app.api.entities.rank_titles") as mock_rank:
        mock_rank.return_value = [
            TitleMatch(normalized_title="x", score=1.0, surface_forms=["Οικονομετρία\xa0 ΙΙ"])
        ]
        response = client.get("/entities/search", params={"q": "x"})

    assert response.json()["results"][0]["title"] == "Οικονομετρία ΙΙ"
