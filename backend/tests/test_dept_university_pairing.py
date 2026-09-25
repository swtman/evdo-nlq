"""Department ↔ university pairing (title-linking plan, branch 3; ADR-028).

A department in EvdoGraph is a (label, university) pair, and many universities
use the SAME name: "νοσηλευτικής" is 20 departments at 19 universities under 5 labels,
"ΛΟΓΙΣΤΙΚΗΣ ΚΑΙ ΧΡΗΜΑΤΟΟΙΚΟΝΟΜΙΚΗΣ" at 24. Grounding used to deduplicate by
label alone, so every shared name collapsed onto one arbitrary university and
the hint could contradict the question ("τμήμα νοσηλευτικής του ΠΑΔΑ" →
"[Department @ ΕΘΝΙΚΟ & ΚΑΠΟΔΙΣΤΡΙΑΚΟ …] ΝΟΣΗΛΕΥΤΙΚΗΣ"). Evidence S11/S28:
the named university was kept in only 135/548 generated questions.

Decision (user, 2026-09-25): keep EVERY pair, never filter by the university
the question names; the hint shows one line per label listing all of its
universities. These tests pin that contract at the three layers that had the
bug: the linker, the window resolver, and the hint formatter.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.grounding.db import DB_PATH
from app.grounding.gazetteer import get_department_index
from app.grounding.hint_lines import _format_entity_lines
from app.grounding.hints import build_grounding_hints
from app.grounding.lexicon import _ENTITY_STOPWORDS
from app.grounding.linker import ResolvedEntity, resolve_mention
from app.grounding.mentions import _resolve_all_windows, _tokenize
from app.grounding.normalize import normalize_greek

PADA = "ΠΑΝΕΠΙΣΤΗΜΙΟ ΔΥΤΙΚΗΣ ΑΤΤΙΚΗΣ"
EKPA = "ΕΘΝΙΚΟ & ΚΑΠΟΔΙΣΤΡΙΑΚΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΑΘΗΝΩΝ"


def _nursing_pairs() -> set[tuple[str, str]]:
    """Every (label, university) pair indexed under the key of "ΝΟΣΗΛΕΥΤΙΚΗΣ"."""
    return {
        (d["department"], d["university"])
        for d in get_department_index()[normalize_greek("ΝΟΣΗΛΕΥΤΙΚΗΣ")]
    }


def _dept(label: str, parent: str) -> ResolvedEntity:
    return ResolvedEntity(label, "department", parent, "exact", 1.0)


# ---------------------------------------------------------------------------
# Linker
# ---------------------------------------------------------------------------


def test_fixture_name_is_really_shared() -> None:
    """Guard the fixture: the KG snapshot must still have the shared name."""
    pairs = _nursing_pairs()
    assert len({u for _, u in pairs}) >= 10
    assert ("ΝΟΣΗΛΕΥΤΙΚΗΣ", PADA) in pairs


def test_exact_match_returns_every_university() -> None:
    """An exact department match keeps one entity per (label, university) pair."""
    got = {
        (e.canonical_label, e.parent_university)
        for e in resolve_mention("νοσηλευτικής")
        if e.entity_type == "department"
    }
    assert got == _nursing_pairs()


def test_fuzzy_match_returns_every_university() -> None:
    """The fuzzy stage expands its best label to all pairs sharing that key.

    "νοσηλευτικη" (nominative) misses the exact index ("νοσηλευτικησ") and
    reaches the fuzzy stage, which used to return a single, arbitrary pair.
    """
    depts = [e for e in resolve_mention("νοσηλευτικη") if e.entity_type == "department"]
    assert depts and all(e.match_method == "fuzzy" for e in depts)
    assert {(e.canonical_label, e.parent_university) for e in depts} == _nursing_pairs()


def test_pairs_are_unique() -> None:
    """Deduplication is by (label, university): no pair appears twice."""
    results = resolve_mention("νοσηλευτικής")
    keys = [(e.canonical_label, e.parent_university) for e in results]
    assert len(keys) == len(set(keys))


# ---------------------------------------------------------------------------
# Window resolver
# ---------------------------------------------------------------------------


def test_window_resolver_keeps_the_named_university() -> None:
    """The resolver no longer collapses shared labels onto one university."""
    q = "ποια μαθηματα προσφερει το τμημα νοσηλευτικης του ΠΑΔΑ"
    ents = _resolve_all_windows(_tokenize(q, _ENTITY_STOPWORDS)).values()
    pairs = {
        (e.canonical_label, e.parent_university) for e in ents if e.entity_type == "department"
    }
    assert ("ΝΟΣΗΛΕΥΤΙΚΗΣ", PADA) in pairs
    # Never filtered by the named university: the other universities stay too.
    assert pairs == _nursing_pairs()


# ---------------------------------------------------------------------------
# Hint formatting
# ---------------------------------------------------------------------------


def test_one_line_per_label_listing_every_university() -> None:
    """Pairs with the same label merge into one line; universities joined by " | "."""
    lines = _format_entity_lines(
        [
            ResolvedEntity(PADA, "university", None, "acronym", 1.0),
            _dept("ΝΟΣΗΛΕΥΤΙΚΗΣ", EKPA),
            _dept("ΝΟΣΗΛΕΥΤΙΚΗΣ (ΑΛΕΞΑΝΔΡΟΥΠΟΛΗ)", "ΔΗΜΟΚΡΙΤΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΡΑΚΗΣ"),
            _dept("ΝΟΣΗΛΕΥΤΙΚΗΣ", PADA),
        ]
    )
    assert lines == [
        f"- [University] {PADA}",
        f"- [Department @ {EKPA} | {PADA}] ΝΟΣΗΛΕΥΤΙΚΗΣ",
        "- [Department @ ΔΗΜΟΚΡΙΤΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΡΑΚΗΣ] ΝΟΣΗΛΕΥΤΙΚΗΣ (ΑΛΕΞΑΝΔΡΟΥΠΟΛΗ)",
    ]


def test_single_university_line_is_unchanged() -> None:
    """A label at one university keeps the pre-branch-3 line format exactly."""
    assert _format_entity_lines([_dept("ΠΛΗΡΟΦΟΡΙΚΗΣ", PADA)]) == [
        f"- [Department @ {PADA}] ΠΛΗΡΟΦΟΡΙΚΗΣ"
    ]


def test_hint_never_contradicts_the_named_university() -> None:
    """End to end: the hint lists the named university for the label."""
    block = build_grounding_hints("ποια μαθήματα προσφέρει το τμήμα νοσηλευτικής του ΠΑΔΑ")
    lines = [ln for ln in block.splitlines() if ln.endswith("] ΝΟΣΗΛΕΥΤΙΚΗΣ")]
    assert len(lines) == 1, block
    assert PADA in lines[0] and EKPA in lines[0]


# ---------------------------------------------------------------------------
# Regression over the real KG (S11's question set, rebuilt from entities.db)
# ---------------------------------------------------------------------------


def _shared_name_cases() -> list[tuple[str, str]]:
    """(label, university) for every label whose normalized name is at >1 university."""
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        return con.execute(
            "select distinct surface, parent from department where norm in ("
            " select norm from department group by norm having count(distinct parent) > 1)"
            " order by surface, parent"
        ).fetchall()
    finally:
        con.close()


@pytest.mark.parametrize("label", ["ΝΟΣΗΛΕΥΤΙΚΗΣ", "ΛΟΓΙΣΤΙΚΗΣ ΚΑΙ ΧΡΗΜΑΤΟΟΙΚΟΝΟΜΙΚΗΣ"])
def test_every_university_of_a_shared_label_is_resolved(label: str) -> None:
    """Typed bare, a shared label resolves to every university that has it."""
    expected = {u for s, u in _shared_name_cases() if s == label}
    ents = _resolve_all_windows(_tokenize(f"τμημα {label.lower()}", _ENTITY_STOPWORDS)).values()
    got = {e.parent_university for e in ents if e.canonical_label == label}
    assert got == expected


def test_named_university_kept_whenever_the_label_is_found() -> None:
    """S11 as a test: if the department label is found, its named university is too.

    Before branch 3 this held for 135 of the 415 questions whose label was found.
    (Labels that are not found at all — mostly long "(…)"-suffixed variants typed
    in full — are a separate recall question, outside this contract.)

    One case per shared label — its alphabetically LAST university — rather than
    all 548 (~26 s; S28 in the evidence record runs them all): the old
    label-only dedup kept the FIRST university in that order, so the last one
    is exactly where it failed.
    """
    last_university: dict[str, str] = {}
    for label, parent in _shared_name_cases():  # ordered by (label, parent)
        last_university[label] = parent

    failures = []
    for label, parent in last_university.items():
        q = f"ποια μαθηματα προσφερει το τμημα {label.lower()} του {parent.lower()}"
        ents = _resolve_all_windows(_tokenize(q, _ENTITY_STOPWORDS)).values()
        parents = {e.parent_university for e in ents if e.canonical_label == label}
        if parents and parent not in parents:
            failures.append((label, parent, sorted(parents)))
    assert not failures, failures[:5]
