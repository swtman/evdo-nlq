"""ΟΝΤΟΛΟΓΙΑ department cards show every exact name with its own universities (ADR-029).

The department search groups rows by ``normalize_greek`` of the name, which
drops a trailing "(…)" — right for FINDING ("νοσηλευτικης" should reach every
variant) but the card used to show one surface per group plus one flat,
unpaired list of universities. So «ΠΡΟΓΡΑΜΜΑ ΣΠΟΥΔΩΝ ΝΟΣΗΛΕΥΤΙΚΗΣ (ΛΑΡΙΣΑ)»
vanished behind «… (ΛΑΜΙΑ)», and the «ΝΟΣΗΛΕΥΤΙΚΗΣ» card listed ΔΠΘ although
ΔΠΘ's department is named «ΝΟΣΗΛΕΥΤΙΚΗΣ (ΑΛΕΞΑΝΔΡΟΥΠΟΛΗ)» — a user copying
the card's name into a query at ΔΠΘ gets nothing.

Contract pinned here:
  - ``TitleMatch.variants`` (department only): exact name → its sorted universities.
  - The API returns them as ``variants: [{name, parents}]``; a group with several
    names is titled by the shared name without its "(…)" (what the group key
    means); a group with one name keeps that exact name as its title.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.entities import router
from app.grounding.normalize import drop_status_suffix
from app.grounding.title_index import TitleMatch, list_titles, rank_titles

DPTH = "ΔΗΜΟΚΡΙΤΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΡΑΚΗΣ"
PADA = "ΠΑΝΕΠΙΣΤΗΜΙΟ ΔΥΤΙΚΗΣ ΑΤΤΙΚΗΣ"
THESSALY = "ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣΣΑΛΙΑΣ"


# ---------------------------------------------------------------------------
# normalize.drop_status_suffix — the same "(…)" rule normalize_greek applies
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ΝΟΣΗΛΕΥΤΙΚΗΣ (ΑΛΕΞΑΝΔΡΟΥΠΟΛΗ)", "ΝΟΣΗΛΕΥΤΙΚΗΣ"),
        ("ΠΡΟΓΡΑΜΜΑ ΣΠΟΥΔΩΝ ΝΟΣΗΛΕΥΤΙΚΗΣ (ΛΑΜΙΑ)", "ΠΡΟΓΡΑΜΜΑ ΣΠΟΥΔΩΝ ΝΟΣΗΛΕΥΤΙΚΗΣ"),
        ("ΝΟΣΗΛΕΥΤΙΚΗΣ", "ΝΟΣΗΛΕΥΤΙΚΗΣ"),
    ],
)
def test_drop_status_suffix(raw: str, expected: str) -> None:
    assert drop_status_suffix(raw) == expected


# ---------------------------------------------------------------------------
# title_index — real entities.db
# ---------------------------------------------------------------------------


def _match(phrase: str, norm: str) -> TitleMatch:
    return next(
        m
        for m in rank_titles(phrase, k=10, entity_class="department")
        if m.normalized_title == norm
    )


def test_every_exact_name_keeps_its_own_universities() -> None:
    nursing = _match("ΝΟΣΗΛΕΥΤΙΚΗΣ", "νοσηλευτικησ")
    assert set(nursing.variants) == {
        "ΝΟΣΗΛΕΥΤΙΚΗΣ",
        "ΝΟΣΗΛΕΥΤΙΚΗΣ (ΑΛΕΞΑΝΔΡΟΥΠΟΛΗ)",
        "ΝΟΣΗΛΕΥΤΙΚΗΣ (ΔΙΔΥΜΟΤΕΙΧΟ)",
        "ΝΟΣΗΛΕΥΤΙΚΗΣ (ΘΕΣΣΑΛΟΝΙΚΗ)",
        "ΝΟΣΗΛΕΥΤΙΚΗΣ (ΚΑΤΑΡΓΗΘΗΚΕ/ΜΕΤΑΦΕΡΘΗΚΕ)",
    }
    assert nursing.variants["ΝΟΣΗΛΕΥΤΙΚΗΣ (ΑΛΕΞΑΝΔΡΟΥΠΟΛΗ)"] == [DPTH]
    assert PADA in nursing.variants["ΝΟΣΗΛΕΥΤΙΚΗΣ"]
    assert DPTH not in nursing.variants["ΝΟΣΗΛΕΥΤΙΚΗΣ"]
    # Nothing lost: the union of the variants' universities is the flat list.
    assert sorted({u for us in nursing.variants.values() for u in us}) == nursing.parents


def test_same_university_variants_are_both_kept() -> None:
    """ΛΑΜΙΑ and ΛΑΡΙΣΑ are both at ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣΣΑΛΙΑΣ; neither may hide the other."""
    programme = _match("ΠΡΟΓΡΑΜΜΑ ΣΠΟΥΔΩΝ ΝΟΣΗΛΕΥΤΙΚΗΣ", "προγραμμα σπουδων νοσηλευτικησ")
    assert programme.variants == {
        "ΠΡΟΓΡΑΜΜΑ ΣΠΟΥΔΩΝ ΝΟΣΗΛΕΥΤΙΚΗΣ (ΛΑΜΙΑ)": [THESSALY],
        "ΠΡΟΓΡΑΜΜΑ ΣΠΟΥΔΩΝ ΝΟΣΗΛΕΥΤΙΚΗΣ (ΛΑΡΙΣΑ)": [THESSALY],
    }


def test_browse_list_carries_the_same_variants() -> None:
    """/entities/list (the «δείτε τα όλα» modal) reads rows through the same helper."""
    listed = {m.normalized_title: m for m in list_titles(entity_class="department")}
    assert listed["νοσηλευτικησ"].variants == _match("ΝΟΣΗΛΕΥΤΙΚΗΣ", "νοσηλευτικησ").variants


@pytest.mark.parametrize(("phrase", "cls"), [("ΑΠΘ", "university"), ("ΦΥΣΙΚΗ", "course")])
def test_other_classes_have_no_variants(phrase: str, cls: str) -> None:
    assert all(m.variants == {} for m in rank_titles(phrase, k=3, entity_class=cls))


# ---------------------------------------------------------------------------
# API — rank_titles/list_titles mocked
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _dept(variants: dict[str, list[str]]) -> TitleMatch:
    return TitleMatch(
        normalized_title="x",
        score=1.0,
        surface_forms=sorted(variants),
        entity_class="department",
        parents=sorted({u for us in variants.values() for u in us}),
        variants=variants,
    )


@pytest.mark.parametrize(
    ("path", "patched"),
    [
        ("/entities/search", "app.api.entities.rank_titles"),
        ("/entities/list", "app.api.entities.list_titles"),
    ],
)
def test_api_returns_each_name_with_its_universities(client, path, patched) -> None:
    match = _dept(
        {
            "ΝΟΣΗΛΕΥΤΙΚΗΣ": [PADA],
            "ΝΟΣΗΛΕΥΤΙΚΗΣ (ΑΛΕΞΑΝΔΡΟΥΠΟΛΗ)": [DPTH],
        }
    )
    with patch(patched, return_value=[match]):
        body = client.get(path, params={"q": "ν", "class": "department"}).json()

    result = body["results"][0]
    assert result["title"] == "ΝΟΣΗΛΕΥΤΙΚΗΣ"
    assert result["variants"] == [
        {"name": "ΝΟΣΗΛΕΥΤΙΚΗΣ", "parents": [PADA]},
        {"name": "ΝΟΣΗΛΕΥΤΙΚΗΣ (ΑΛΕΞΑΝΔΡΟΥΠΟΛΗ)", "parents": [DPTH]},
    ]
    assert result["parents"] == [DPTH, PADA]  # unchanged flat field


def test_group_title_drops_the_tail_only_when_several_names(client) -> None:
    """ΛΑΜΙΑ + ΛΑΡΙΣΑ → titled by the shared name; a lone tailed name keeps its tail."""
    several = _dept(
        {
            "ΠΡΟΓΡΑΜΜΑ ΣΠΟΥΔΩΝ ΝΟΣΗΛΕΥΤΙΚΗΣ (ΛΑΜΙΑ)": [THESSALY],
            "ΠΡΟΓΡΑΜΜΑ ΣΠΟΥΔΩΝ ΝΟΣΗΛΕΥΤΙΚΗΣ (ΛΑΡΙΣΑ)": [THESSALY],
        }
    )
    lone = _dept({"ΑΙΣΘΗΤΙΚΗΣ ΚΑΙ ΚΟΣΜΗΤΟΛΟΓΙΑΣ (ΚΑΤΑΡΓΗΘΗΚΕ/ΜΕΤΑΦΕΡΘΗΚΕ)": ["ΤΕΙ ΑΘΗΝΑΣ"]})
    with patch("app.api.entities.rank_titles", return_value=[several, lone]):
        results = client.get("/entities/search", params={"q": "x", "class": "department"}).json()[
            "results"
        ]

    assert results[0]["title"] == "ΠΡΟΓΡΑΜΜΑ ΣΠΟΥΔΩΝ ΝΟΣΗΛΕΥΤΙΚΗΣ"
    assert results[1]["title"] == "ΑΙΣΘΗΤΙΚΗΣ ΚΑΙ ΚΟΣΜΗΤΟΛΟΓΙΑΣ (ΚΑΤΑΡΓΗΘΗΚΕ/ΜΕΤΑΦΕΡΘΗΚΕ)"


def test_non_department_results_have_empty_variants(client) -> None:
    course = TitleMatch(normalized_title="x", score=1.0, surface_forms=["X"], entity_class="course")
    with patch("app.api.entities.rank_titles", return_value=[course]):
        result = client.get("/entities/search", params={"q": "X"}).json()["results"][0]
    assert result["variants"] == []
    assert result["title"] == "X"
