"""ΟΝΤΟΛΟΓΙΑ page search — the word rules (ADR-030, plan step 3).

``title_index.word_search`` implements the rules measured by the S35 v2.2 prototype:
every typed word must match a word of ONE exact name — the same word, the start of a word,
or a small typo (1 from 5 letters, 2 from 8) — never inside a longer word; connectors match
only whole; optional words (connectors + class words) need not match; «&»=«και» etc. via
``normalize.search_fold``; ranking: literal exact name > exact after synonyms > worst word
match (exact < start < typo) > fewer typos > fewer words > name.

Rule tests run on small in-memory databases (``_search``); the last section runs the real
``entities.db`` through ``search_names``.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.grounding.normalize import normalize_greek
from app.grounding.schema import create_schema, sync_search_index
from app.grounding.title_index.word_search import MIN_QUERY_LETTERS, _search, search_names

NAMES = [
    ("ΝΟΣΗΛΕΥΤΙΚΗΣ", "ΠΑΝΕΠΙΣΤΗΜΙΟ ΠΑΤΡΩΝ"),
    ("ΝΟΣΗΛΕΥΤΙΚΗΣ (ΑΛΕΞΑΝΔΡΟΥΠΟΛΗ)", "ΔΗΜΟΚΡΙΤΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΡΑΚΗΣ"),
    ("ΠΡΟΓΡΑΜΜΑ ΣΠΟΥΔΩΝ ΝΟΣΗΛΕΥΤΙΚΗΣ (ΛΑΜΙΑ)", "ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣΣΑΛΙΑΣ"),
    ("ΠΡΟΓΡΑΜΜΑ ΣΠΟΥΔΩΝ ΝΟΣΗΛΕΥΤΙΚΗΣ (ΛΑΡΙΣΑ)", "ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣΣΑΛΙΑΣ"),
    ("ΖΩΙΚΗΣ ΠΑΡΑΓΩΓΗΣ", "ΤΕΙ ΗΠΕΙΡΟΥ"),
    ("ΠΑΙΔΑΓΩΓΙΚΟ ΤΜΗΜΑ ΕΙΔΙΚΗΣ ΑΓΩΓΗΣ", "ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣΣΑΛΙΑΣ"),
    ("ΕΜΠΟΡΙΑΣ & ΔΙΑΦΗΜΙΣΗΣ", "ΤΕΙ ΑΘΗΝΑΣ"),
    ("ΑΝΑΚΑΙΝΙΣΗΣ ΚΑΙ ΑΠΟΚΑΤΑΣΤΑΣΗΣ ΚΤΙΡΙΩΝ", "ΤΕΙ ΑΘΗΝΑΣ"),
    ("ΑΝΑΚΑΙΝΙΣΗΣ & ΑΠΟΚΑΤΑΣΤΑΣΗΣ ΚΤΙΡΙΩΝ", "ΤΕΙ ΠΑΤΡΑΣ"),
    ("ΠΛΗΡΟΦΟΡΙΚΗΣ", "ΠΑΝΕΠΙΣΤΗΜΙΟ ΠΕΙΡΑΙΩΣ"),
    ("ΠΛΗΡΟΦΟΡΙΚΗ", "ΙΟΝΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ"),
    ("ΜΗΧΑΝΙΚΩΝ ΠΛΗΡΟΦΟΡΙΚΗΣ Τ.Ε.", "ΤΕΙ ΗΠΕΙΡΟΥ"),
]


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_schema(c)
    c.executemany(
        "INSERT INTO department(norm, family, surface, parent) VALUES (?, NULL, ?, ?)",
        [(normalize_greek(s), s, p) for s, p in NAMES],
    )
    sync_search_index(c, "department")
    return c


def names(conn: sqlite3.Connection, q: str, limit: int = 100, offset: int = 0) -> list[str]:
    """The first exact name of every result, in rank order (readable assertions)."""
    matches, _ = _search(conn, q, entity_class="department", limit=limit, offset=offset)
    return [m.surface_forms[0] for m in matches]


# --- matching ------------------------------------------------------------------


@pytest.mark.parametrize("q", ["", "   ", "ν", "Ν.", "*"])
def test_fewer_than_two_letters_returns_nothing(conn, q) -> None:
    assert MIN_QUERY_LETTERS == 2
    assert _search(conn, q, entity_class="department", limit=10, offset=0) == ([], 0)


def test_start_of_word(conn) -> None:
    assert "ΝΟΣΗΛΕΥΤΙΚΗΣ" in names(conn, "νοσηλ")


def test_word_inside_the_tail_is_searchable(conn) -> None:
    assert names(conn, "λαρισα") == ["ΠΡΟΓΡΑΜΜΑ ΣΠΟΥΔΩΝ ΝΟΣΗΛΕΥΤΙΚΗΣ (ΛΑΜΙΑ)"]  # group's first name


def test_no_match_inside_a_longer_word(conn) -> None:
    """«αγωγης» is inside «παραγωγης» — not a word, not a word start: excluded."""
    assert names(conn, "αγωγης") == ["ΠΑΙΔΑΓΩΓΙΚΟ ΤΜΗΜΑ ΕΙΔΙΚΗΣ ΑΓΩΓΗΣ"]


def test_every_typed_word_must_match_one_name(conn) -> None:
    assert names(conn, "νοσηλευτικης λαμια") == ["ΠΡΟΓΡΑΜΜΑ ΣΠΟΥΔΩΝ ΝΟΣΗΛΕΥΤΙΚΗΣ (ΛΑΜΙΑ)"]
    assert names(conn, "νοσηλευτικης πειραια") == []


def test_one_typo_from_five_letters_none_below(conn) -> None:
    assert "ΝΟΣΗΛΕΥΤΙΚΗΣ" in names(conn, "νοσηλευτκης")  # one letter missing
    assert names(conn, "ζωκη") == []  # 4 letters: no typo allowed, and not a word start


def test_connectors_match_only_whole(conn) -> None:
    """«κα» must not reach every name with «και» (from «&» or written out)."""
    assert names(conn, "κα") == []
    assert names(conn, "και") != []  # the whole connector still matches (only-optional query)


def test_optional_words_need_not_match(conn) -> None:
    assert names(conn, "τμημα νοσηλευτικης") == names(conn, "νοσηλευτικης")
    assert names(conn, "τμήμα νοσηλευτικής") == names(conn, "νοσηλευτικης")


def test_query_of_only_optional_words_is_matched_normally(conn) -> None:
    assert names(conn, "τμημα") == ["ΠΑΙΔΑΓΩΓΙΚΟ ΤΜΗΜΑ ΕΙΔΙΚΗΣ ΑΓΩΓΗΣ"]


def test_synonym_ampersand(conn) -> None:
    assert names(conn, "εμποριας και διαφημισης") == ["ΕΜΠΟΡΙΑΣ & ΔΙΑΦΗΜΙΣΗΣ"]


def test_dotted_abbreviation(conn) -> None:
    assert names(conn, "μηχανικων πληροφορικης τε") == ["ΜΗΧΑΝΙΚΩΝ ΠΛΗΡΟΦΟΡΙΚΗΣ Τ.Ε."]


# --- ranking -------------------------------------------------------------------


def test_literal_exact_name_beats_synonym_twin(conn) -> None:
    assert (
        names(conn, "ΑΝΑΚΑΙΝΙΣΗΣ ΚΑΙ ΑΠΟΚΑΤΑΣΤΑΣΗΣ ΚΤΙΡΙΩΝ")[0]
        == "ΑΝΑΚΑΙΝΙΣΗΣ ΚΑΙ ΑΠΟΚΑΤΑΣΤΑΣΗΣ ΚΤΙΡΙΩΝ"
    )
    assert (
        names(conn, "ΑΝΑΚΑΙΝΙΣΗΣ & ΑΠΟΚΑΤΑΣΤΑΣΗΣ ΚΤΙΡΙΩΝ")[0]
        == "ΑΝΑΚΑΙΝΙΣΗΣ & ΑΠΟΚΑΤΑΣΤΑΣΗΣ ΚΤΙΡΙΩΝ"
    )


def test_fewer_typos_rank_first(conn) -> None:
    """«πληροφορκης»: 1 edit from ΠΛΗΡΟΦΟΡΙΚΗΣ, 2 from ΠΛΗΡΟΦΟΡΙΚΗ."""
    ranked = names(conn, "πληροφορκης")
    assert ranked.index("ΠΛΗΡΟΦΟΡΙΚΗΣ") < ranked.index("ΠΛΗΡΟΦΟΡΙΚΗ")


def test_exact_word_before_word_start_before_typo_and_shorter_first(conn) -> None:
    ranked = names(conn, "πληροφορικης")
    assert ranked[:2] == ["ΠΛΗΡΟΦΟΡΙΚΗΣ", "ΜΗΧΑΝΙΚΩΝ ΠΛΗΡΟΦΟΡΙΚΗΣ Τ.Ε."]


# --- paging, safety, shape -----------------------------------------------------------


def test_total_and_pages(conn) -> None:
    everything, total = _search(conn, "νοσηλ", entity_class="department", limit=100, offset=0)
    # Two results: ΝΟΣΗΛΕΥΤΙΚΗΣ and ΝΟΣΗΛΕΥΤΙΚΗΣ (ΑΛΕΞΑΝΔΡΟΥΠΟΛΗ) share one group key
    # (ADR-029: one result, several exact names); the ΛΑΜΙΑ/ΛΑΡΙΣΑ programme is the other.
    assert total == len(everything) == 2
    page2, total2 = _search(conn, "νοσηλ", entity_class="department", limit=1, offset=1)
    assert total2 == 2
    assert [m.normalized_title for m in page2] == [everything[1].normalized_title]


@pytest.mark.parametrize(
    "q", ['"', '"νοσηλ', "νοσηλ*", "NEAR(νοσηλ)", "νοσηλ OR", "-νοσηλ", "AND OR NOT", "^νο"]
)
def test_fts_syntax_in_input_is_harmless(conn, q) -> None:
    matches, total = _search(conn, q, entity_class="department", limit=10, offset=0)
    assert total == len(matches)


def test_result_carries_every_name_and_university(conn) -> None:
    [programme] = _search(conn, "λαρισα", entity_class="department", limit=10, offset=0)[0]
    assert programme.entity_class == "department"
    assert programme.variants == {
        "ΠΡΟΓΡΑΜΜΑ ΣΠΟΥΔΩΝ ΝΟΣΗΛΕΥΤΙΚΗΣ (ΛΑΜΙΑ)": ["ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣΣΑΛΙΑΣ"],
        "ΠΡΟΓΡΑΜΜΑ ΣΠΟΥΔΩΝ ΝΟΣΗΛΕΥΤΙΚΗΣ (ΛΑΡΙΣΑ)": ["ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣΣΑΛΙΑΣ"],
    }


def test_unknown_class_rejected(conn) -> None:
    with pytest.raises(ValueError):
        _search(conn, "νοσηλ", entity_class="course", limit=10, offset=0)


# --- the committed entities.db --------------------------------------------------------


def top(q: str, cls: str) -> str:
    matches, _ = search_names(q, entity_class=cls, limit=50)
    return matches[0].normalized_title if matches else ""


@pytest.mark.parametrize(
    ("q", "cls", "expected_top"),
    [
        # S35 M7 natural phrasings (each #1 for the rules)
        ("αριστοτελειο θεσσαλονικης", "university", "αριστοτελειο πανεπιστημιο θεσ/νικησ"),
        ("ΑΠΘ", "university", "αριστοτελειο πανεπιστημιο θεσ/νικησ"),
        ("καποδιστριακο", "university", "εθνικο & καποδιστριακο πανεπιστημιο αθηνων"),
        ("πανεπιστημιο του αιγαιου", "university", "πανεπιστημιο αιγαιου"),
        ("τμημα πληροφορικης", "department", "πληροφορικησ"),
        ("τμήμα νοσηλευτικής", "department", "νοσηλευτικησ"),
        ("νομικη σχολη", "department", "νομικησ"),
        ("πληροφορκης", "department", "πληροφορικησ"),
        ("μηχανολογων μηχανικων τε", "department", "μηχανολογων μηχανικων τ.ε."),
    ],
)
def test_real_db_natural_phrasings(q: str, cls: str, expected_top: str) -> None:
    assert top(q, cls) == expected_top


def test_real_db_larisa_returns_all_four() -> None:
    matches, total = search_names("λαρισα", entity_class="department", limit=50)
    assert total == 4
    assert all(any("ΛΑΡΙΣΑ" in s for s in m.surface_forms) for m in matches)
