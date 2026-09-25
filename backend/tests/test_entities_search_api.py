"""GET /entities/search — the ΟΝΤΟΛΟΓΙΑ contract after ADR-030 (plan step 5).

* university/department -> the word search (``search_names``), with ``offset`` and a
  real ``total`` (all matches), so the card and the modal can show one result list;
* course/book -> ``rank_titles`` as before;
* fewer than 2 letters -> ``results: [], total: 0`` for EVERY class, no search run;
* every result carries the raw KG literals (C2 "exact form"): ``literals`` and, per
  department variant, ``literal`` — whitespace untouched, unlike the display ``title``.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.entities import router
from app.grounding.title_index import TitleMatch


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.mark.parametrize("cls", ["course", "book", "university", "department"])
@pytest.mark.parametrize("q", ["ν", "Ν.", " x ", "*"])
def test_fewer_than_two_letters_returns_empty_without_searching(client, cls, q) -> None:
    with (
        patch("app.api.entities.rank_titles") as mock_rank,
        patch("app.api.entities.search_names") as mock_search,
    ):
        body = client.get("/entities/search", params={"q": q, "class": cls}).json()
    assert body["results"] == [] and body["total"] == 0
    mock_rank.assert_not_called()
    mock_search.assert_not_called()


def test_offset_and_total_come_from_the_word_search(client) -> None:
    match = TitleMatch(
        normalized_title="x", score=1.0, surface_forms=["X"], entity_class="department"
    )
    with patch("app.api.entities.search_names", return_value=([match], 37)) as mock_search:
        body = client.get(
            "/entities/search",
            params={"q": "νοσηλ", "class": "department", "limit": 10, "offset": 20},
        ).json()
    mock_search.assert_called_once_with("νοσηλ", entity_class="department", limit=10, offset=20)
    assert body["total"] == 37  # all matches, not the page length
    assert len(body["results"]) == 1


def test_negative_offset_rejected(client) -> None:
    assert client.get("/entities/search", params={"q": "νοσ", "offset": -1}).status_code == 422


def test_course_path_unchanged_and_pages_by_offset(client) -> None:
    ranked = [
        TitleMatch(
            normalized_title=f"t{i}",
            score=1.0 - i / 10,
            surface_forms=[f"T{i}"],
            entity_class="course",
        )
        for i in range(5)
    ]
    with patch("app.api.entities.rank_titles", return_value=ranked) as mock_rank:
        body = client.get("/entities/search", params={"q": "αρχ", "limit": 2, "offset": 3}).json()
    mock_rank.assert_called_once_with("αρχ", k=5, entity_class="course")  # offset + limit
    assert [r["title"] for r in body["results"]] == ["T3", "T4"]
    assert body["total"] == 5


def test_literals_are_raw_and_title_is_tidy(client) -> None:
    raw = "\tΑΝΕΞΑΡΤΗΤΗ ΣΠΟΥΔΗ 2"
    match = TitleMatch(normalized_title="x", score=1.0, surface_forms=[raw], entity_class="course")
    with patch("app.api.entities.rank_titles", return_value=[match]):
        result = client.get("/entities/search", params={"q": "ανεξ"}).json()["results"][0]
    assert result["title"] == "ΑΝΕΞΑΡΤΗΤΗ ΣΠΟΥΔΗ 2"
    assert result["literals"] == [raw]  # the tab survives for copying


def test_literals_deduplicated_in_order(client) -> None:
    match = TitleMatch(
        normalized_title="x",
        score=1.0,
        surface_forms=["ΒΑΣΕΙΣ ΔΕΔΟΜΕΝΩΝ", "Βάσεις Δεδομένων", "ΒΑΣΕΙΣ ΔΕΔΟΜΕΝΩΝ"],
        entity_class="course",
    )
    with patch("app.api.entities.rank_titles", return_value=[match]):
        result = client.get("/entities/search", params={"q": "βασ"}).json()["results"][0]
    assert result["literals"] == ["ΒΑΣΕΙΣ ΔΕΔΟΜΕΝΩΝ", "Βάσεις Δεδομένων"]


def test_variant_literal_is_raw(client) -> None:
    raw = "ΠΑΙΔΑΓΩΓΙΚΟ  ΔΗΜΟΤΙΚΗΣ ΕΚΠΑΙΔΕΥΣΗΣ (ΚΑΤΑΡΓΗΘΗΚΕ/ΜΕΤΑΦΕΡΘΗΚΕ)"  # double space
    match = TitleMatch(
        normalized_title="x",
        score=1.0,
        surface_forms=[raw],
        entity_class="department",
        parents=["ΤΕΙ ΚΡΗΤΗΣ"],
        variants={raw: ["ΤΕΙ ΚΡΗΤΗΣ"]},
    )
    with patch("app.api.entities.search_names", return_value=([match], 1)):
        result = client.get("/entities/search", params={"q": "παιδ", "class": "department"}).json()[
            "results"
        ][0]
    [variant] = result["variants"]
    assert variant["name"] == "ΠΑΙΔΑΓΩΓΙΚΟ ΔΗΜΟΤΙΚΗΣ ΕΚΠΑΙΔΕΥΣΗΣ (ΚΑΤΑΡΓΗΘΗΚΕ/ΜΕΤΑΦΕΡΘΗΚΕ)"
    assert variant["literal"] == raw


# --- the committed entities.db --------------------------------------------------------


def test_real_db_pages_add_up_to_the_full_list(client) -> None:
    """Card and modal show one list: page 1 + page 2 == the whole ranked list."""
    full = client.get(
        "/entities/search", params={"q": "πληροφορικης", "class": "department", "limit": 100}
    ).json()
    assert full["total"] == len(full["results"]) > 8
    p1 = client.get(
        "/entities/search",
        params={"q": "πληροφορικης", "class": "department", "limit": 8, "offset": 0},
    ).json()
    p2 = client.get(
        "/entities/search",
        params={"q": "πληροφορικης", "class": "department", "limit": 100, "offset": 8},
    ).json()
    assert p1["total"] == p2["total"] == full["total"]
    assert [r["title"] for r in p1["results"] + p2["results"]] == [
        r["title"] for r in full["results"]
    ]


def test_real_db_larisa(client) -> None:
    body = client.get("/entities/search", params={"q": "λαρισα", "class": "department"}).json()
    assert body["total"] == 4
