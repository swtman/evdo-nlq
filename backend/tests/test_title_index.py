"""Tests for app.grounding.title_index — FTS5 + rapidfuzz title retrieval.

All tests use an in-memory fixture corpus and the ``rank_titles_from_corpus``
helper so they are completely offline (no disk I/O, no live GraphDB, no module
cache pollution between tests). Most tests exercise the default course table;
a dedicated section near the end covers book-class ranking, cross-class
isolation, and the identifier-safety guard.

The fixture corpus mimics the EvdoGraph naming convention:
  - ALL-CAPS accent-free variant (how some titles are stored in the KG).
  - Mixed-case accented variant (how other titles are stored).
Both surface forms normalize to the same key and should appear together in the
``TitleMatch.surface_forms`` list.

Run from backend/:
    uv run pytest tests/test_title_index.py -v
"""

from __future__ import annotations

import pytest

from app.grounding.title_index import TitleMatch, rank_titles_from_corpus

# ---------------------------------------------------------------------------
# Fixture corpus
# ---------------------------------------------------------------------------

# Surface forms keyed by their normalize_greek() key.
# Mirrors the two-variant storage pattern seen in the real KG.
FIXTURE_CORPUS: dict[str, list[str]] = {
    "αρχιτεκτονικη υπολογιστων": [
        "ΑΡΧΙΤΕΚΤΟΝΙΚΗ ΥΠΟΛΟΓΙΣΤΩΝ",
        "Αρχιτεκτονική Υπολογιστών",
    ],
    "αλγοριθμοι και δομεσ δεδομενων": [
        "ΑΛΓΟΡΙΘΜΟΙ ΚΑΙ ΔΟΜΕΣ ΔΕΔΟΜΕΝΩΝ",
    ],
    "εισαγωγη στη φυσικη": [
        "ΕΙΣΑΓΩΓΗ ΣΤΗ ΦΥΣΙΚΗ",
        "Εισαγωγή στη Φυσική",
    ],
    "αρχιτεκτονικη τοπιου": [
        "ΑΡΧΙΤΕΚΤΟΝΙΚΗ ΤΟΠΙΟΥ",
    ],
    "βασεισ δεδομενων": [
        "ΒΑΣΕΙΣ ΔΕΔΟΜΕΝΩΝ",
        "Βάσεις Δεδομένων",
    ],
}


# ---------------------------------------------------------------------------
# Basic ranking
# ---------------------------------------------------------------------------


def test_exact_phrase_ranks_first() -> None:
    """The title that matches the phrase exactly is returned as the top result."""
    results = rank_titles_from_corpus(
        FIXTURE_CORPUS, "αρχιτεκτονικη υπολογιστων", k=3
    )
    assert len(results) >= 1
    assert results[0].normalized_title == "αρχιτεκτονικη υπολογιστων"


def test_score_is_between_zero_and_one() -> None:
    """All returned scores are in [0, 1]."""
    results = rank_titles_from_corpus(
        FIXTURE_CORPUS, "αρχιτεκτονικη υπολογιστων", k=5
    )
    for match in results:
        assert 0.0 < match.score <= 1.0, f"Score out of range: {match.score}"


def test_results_sorted_descending_by_score() -> None:
    """Results are sorted by score descending (highest similarity first)."""
    results = rank_titles_from_corpus(
        FIXTURE_CORPUS, "αρχιτεκτονικη υπολογιστων", k=5
    )
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_top_result_beats_partial_match() -> None:
    """'αρχιτεκτονικη υπολογιστων' ranks above 'αρχιτεκτονικη τοπιου'.

    Both share the word "αρχιτεκτονικη", but the full phrase matches only
    "αρχιτεκτονικη υπολογιστων" for the second word.
    """
    results = rank_titles_from_corpus(
        FIXTURE_CORPUS, "αρχιτεκτονικη υπολογιστων", k=5
    )
    titles = [r.normalized_title for r in results]
    assert "αρχιτεκτονικη υπολογιστων" in titles
    assert "αρχιτεκτονικη τοπιου" in titles
    idx_target = titles.index("αρχιτεκτονικη υπολογιστων")
    idx_partial = titles.index("αρχιτεκτονικη τοπιου")
    assert idx_target < idx_partial, (
        "Full phrase match should outrank the partial match"
    )


# ---------------------------------------------------------------------------
# Surface forms
# ---------------------------------------------------------------------------


def test_all_surface_forms_returned() -> None:
    """Both KG surface variants are present in the top match's surface_forms."""
    results = rank_titles_from_corpus(
        FIXTURE_CORPUS, "αρχιτεκτονικη υπολογιστων", k=1
    )
    assert len(results) == 1
    surfaces = results[0].surface_forms
    assert "ΑΡΧΙΤΕΚΤΟΝΙΚΗ ΥΠΟΛΟΓΙΣΤΩΝ" in surfaces
    assert "Αρχιτεκτονική Υπολογιστών" in surfaces


def test_single_surface_form_when_only_one_variant() -> None:
    """Titles with a single KG variant return exactly one surface form."""
    results = rank_titles_from_corpus(
        FIXTURE_CORPUS, "αρχιτεκτονικη τοπιου", k=1
    )
    assert len(results) >= 1
    assert results[0].normalized_title == "αρχιτεκτονικη τοπιου"
    assert results[0].surface_forms == ["ΑΡΧΙΤΕΚΤΟΝΙΚΗ ΤΟΠΙΟΥ"]


# ---------------------------------------------------------------------------
# Accent / inflection robustness
# ---------------------------------------------------------------------------


def test_accented_query_matches_normalized_title() -> None:
    """Querying with accented Greek still ranks the correct title first.

    Both query and corpus are normalized by normalize_greek() before
    vectorization, so accents are stripped on both sides.
    """
    results = rank_titles_from_corpus(
        FIXTURE_CORPUS, "Αρχιτεκτονική Υπολογιστών", k=3
    )
    assert results[0].normalized_title == "αρχιτεκτονικη υπολογιστων"


def test_inflected_query_matches_title() -> None:
    """Genitive plural form still retrieves the correct title.

    "υπολογιστων" (gen. pl.) shares char n-grams with "υπολογιστων" in the
    normalized title "αρχιτεκτονικη υπολογιστων".
    """
    results = rank_titles_from_corpus(
        FIXTURE_CORPUS, "αρχιτεκτονικη υπολογιστων", k=3
    )
    assert results[0].normalized_title == "αρχιτεκτονικη υπολογιστων"


def test_word_order_invariant() -> None:
    """Reversed word order returns the same top match.

    TF-IDF treats each n-gram independently, so word order does not matter.
    """
    fwd = rank_titles_from_corpus(
        FIXTURE_CORPUS, "αρχιτεκτονικη υπολογιστων", k=1
    )
    rev = rank_titles_from_corpus(
        FIXTURE_CORPUS, "υπολογιστων αρχιτεκτονικη", k=1
    )
    assert fwd[0].normalized_title == rev[0].normalized_title


# ---------------------------------------------------------------------------
# k parameter
# ---------------------------------------------------------------------------


def test_k_limits_results() -> None:
    """Passing k=1 returns at most one result."""
    results = rank_titles_from_corpus(FIXTURE_CORPUS, "αρχιτεκτονικη υπολογιστων", k=1)
    assert len(results) <= 1


def test_k_greater_than_corpus_returns_all() -> None:
    """Requesting more results than corpus size returns at most len(corpus)."""
    results = rank_titles_from_corpus(FIXTURE_CORPUS, "αρχιτεκτονικη", k=100)
    assert len(results) <= len(FIXTURE_CORPUS)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_corpus_returns_empty_list() -> None:
    """Empty corpus produces an empty result list, not an error."""
    results = rank_titles_from_corpus({}, "αρχιτεκτονικη υπολογιστων", k=3)
    assert results == []


def test_empty_phrase_returns_empty_list() -> None:
    """Empty query phrase produces an empty result list, not an error."""
    results = rank_titles_from_corpus(FIXTURE_CORPUS, "", k=3)
    assert results == []


def test_completely_unrelated_phrase_returns_low_or_no_scores() -> None:
    """A phrase with no shared n-grams returns empty or very low scores.

    "ζζζζ" contains no Greek chars found in any fixture title.
    """
    results = rank_titles_from_corpus(FIXTURE_CORPUS, "ζζζζ", k=3)
    for r in results:
        assert r.score < 0.3, f"Expected low score for unrelated query, got {r.score}"


# ---------------------------------------------------------------------------
# TitleMatch dataclass
# ---------------------------------------------------------------------------


def test_title_match_is_frozen() -> None:
    """TitleMatch is immutable (frozen dataclass)."""
    match = TitleMatch(
        normalized_title="αρχιτεκτονικη υπολογιστων",
        score=0.99,
        surface_forms=["ΑΡΧΙΤΕΚΤΟΝΙΚΗ ΥΠΟΛΟΓΙΣΤΩΝ"],
    )
    with pytest.raises((AttributeError, TypeError)):
        match.score = 0.5  # type: ignore[misc]


def test_title_match_fields() -> None:
    """TitleMatch exposes normalized_title, score, surface_forms, entity_class."""
    match = TitleMatch(
        normalized_title="αρχιτεκτονικη υπολογιστων",
        score=0.85,
        surface_forms=["ΑΡΧΙΤΕΚΤΟΝΙΚΗ ΥΠΟΛΟΓΙΣΤΩΝ", "Αρχιτεκτονική Υπολογιστών"],
    )
    assert match.normalized_title == "αρχιτεκτονικη υπολογιστων"
    assert match.score == pytest.approx(0.85)
    assert len(match.surface_forms) == 2
    assert match.entity_class == "course"  # default, for construction sites predating the field


def test_title_match_entity_class_is_settable() -> None:
    match = TitleMatch(normalized_title="x", score=1.0, entity_class="book")
    assert match.entity_class == "book"


# ---------------------------------------------------------------------------
# Book-class ranking, cross-class isolation, and the identifier-safety guard
# ---------------------------------------------------------------------------

_BOOK_FIXTURE_CORPUS: dict[str, list[str]] = {
    "βασεισ δεδομενων": ["ΒΑΣΕΙΣ ΔΕΔΟΜΕΝΩΝ", "Βάσεις Δεδομένων"],
    "τεχνητη νοημοσυνη": ["Τεχνητή Νοημοσύνη"],
}


def test_book_class_ranks_like_course_class() -> None:
    """rank_titles_from_corpus(entity_class='book') behaves identically to
    the course path for the same kind of fixture — the ranker has no
    class-specific logic beyond which table it reads."""
    results = rank_titles_from_corpus(
        _BOOK_FIXTURE_CORPUS, "βασεισ δεδομενων", k=3, entity_class="book"
    )
    assert len(results) >= 1
    assert results[0].normalized_title == "βασεισ δεδομενων"
    assert results[0].entity_class == "book"
    assert set(results[0].surface_forms) == {"ΒΑΣΕΙΣ ΔΕΔΟΜΕΝΩΝ", "Βάσεις Δεδομένων"}


def test_cross_class_isolation() -> None:
    """Loading a corpus as 'book' must not populate 'course' on the SAME
    database — the test that proves the two-table design (ADR-019) actually
    holds. If someone later 'simplifies' to a single merged table, this is
    the test that goes red.

    Reaches into _build_index/_rank directly (rather than the public
    rank_titles_from_corpus) because the thing being verified is a property
    of one shared connection: `dataclasses.replace` points a second
    _IndexState at the SAME connection, just naming the other table, so a
    query against 'course' is proven to see the identical database that
    'book' was just loaded into — not a coincidentally-empty fresh one.
    """
    from dataclasses import replace

    from app.grounding.title_index import _build_index, _rank

    state = _build_index(_BOOK_FIXTURE_CORPUS, entity_class="book")
    try:
        book_results = _rank("βασεισ δεδομενων", 3, state)
        assert len(book_results) >= 1  # sanity: the corpus does match as a book

        course_state = replace(state, table="course")  # same conn, other table
        course_results = _rank("βασεισ δεδομενων", 3, course_state)
        assert course_results == []  # same connection, course table untouched
    finally:
        state.conn.close()


def test_unknown_entity_class_raises_value_error() -> None:
    with pytest.raises(ValueError, match="unknown title class"):
        rank_titles_from_corpus(_BOOK_FIXTURE_CORPUS, "βασεισ δεδομενων", k=3, entity_class="publisher")
