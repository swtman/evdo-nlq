"""Tests for app.grounding.hints — the grounding orchestrator.

Tests are written before the implementation (TDD).  They verify:
  - Empty / stopword-only input returns exactly "".
  - Acronym entity detection produces the expected canonical label and type tag.
  - Topic stemming produces the expected stem and section header.
  - Combined entity + stem questions produce both sections.
  - The return value is exactly "" (not whitespace) when nothing fires.
"""

from app.grounding.hints import build_grounding_hints


# ---------------------------------------------------------------------------
# Empty / no-entity-no-stem cases
# ---------------------------------------------------------------------------


def test_empty_question_returns_empty() -> None:
    """Empty string must return exactly '' — the pipeline skips injection."""
    assert build_grounding_hints("") == ""


def test_no_entity_no_stem_returns_empty() -> None:
    """Question containing only stopwords or short tokens must return ''."""
    assert build_grounding_hints("τι και η") == ""


def test_returns_empty_string_not_whitespace() -> None:
    """Return value must be '' not '\\n' or '  ' when nothing is found."""
    result = build_grounding_hints("και η το")
    assert result == ""


# ---------------------------------------------------------------------------
# Entity detection
# ---------------------------------------------------------------------------


def test_apth_acronym_detected() -> None:
    """ΑΠΘ must resolve to its canonical label via the acronym stage."""
    result = build_grounding_hints("ποια βιβλία προτείνει το ΑΠΘ;")
    assert "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ" in result
    assert "[University]" in result


def test_entities_section_header_present_when_entity_found() -> None:
    """Resolved entities section header must appear when at least one entity fires."""
    result = build_grounding_hints("ΑΠΘ")
    assert "Entities" in result


# ---------------------------------------------------------------------------
# Topic stem detection
# ---------------------------------------------------------------------------


def test_stem_in_result() -> None:
    """'αλγοριθμων' (genitive) must produce stem 'αλγορ'."""
    result = build_grounding_hints("βιβλία αλγοριθμων")
    assert "αλγορ" in result
    assert "Topic stems" in result


def test_no_entities_only_stem() -> None:
    """When only stems fire (no recognized entity), the entity section is absent."""
    result = build_grounding_hints("βιβλία αλγοριθμων")
    assert "[University]" not in result
    assert "αλγορ" in result


# ---------------------------------------------------------------------------
# Combined entity + stem
# ---------------------------------------------------------------------------


def test_combined_entity_and_stem() -> None:
    """Both sections must appear when the question has an entity AND a topic word."""
    result = build_grounding_hints("ποια βιβλία αλγορίθμων προτείνει το ΑΠΘ;")
    assert "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ" in result
    assert "αλγορ" in result
    assert "Entities" in result
    assert "Topic stems" in result


# ---------------------------------------------------------------------------
# Format / structure checks
# ---------------------------------------------------------------------------


def test_entity_section_absent_when_no_entity() -> None:
    """'Entities' section header must NOT appear when no entity resolves.

    'αλγοριθμων' and 'κβαντικων' are topic words that do not match any
    university or department in the EvdoGraph KG gazetteer.
    """
    result = build_grounding_hints("αλγοριθμων κβαντικων")
    # Neither word is a KG entity name — only stems should appear.
    assert "Entities" not in result


def test_stem_section_absent_when_no_stem() -> None:
    """'Topic stems' section must NOT appear when only entities fire and no useful stems."""
    # ΑΠΘ itself: 3 chars after normalization — filtered before stemming even runs.
    # The stopwords filter should eliminate "ποια", "το"; no non-entity non-stopword
    # long-enough tokens remain to produce stems.
    result = build_grounding_hints("το ΑΠΘ")
    # ΑΠΘ resolves as entity; no other tokens long enough for stemming
    assert "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ" in result
    assert "Topic stems" not in result


def test_output_starts_with_section_heading() -> None:
    """Non-empty output must start with the markdown '## Resolved entities' heading."""
    result = build_grounding_hints("ΑΠΘ αλγοριθμων")
    assert result.startswith("## Resolved entities")


def test_stem_bullet_contains_stem() -> None:
    """Each stem must appear as a bullet line '- <stem>'."""
    result = build_grounding_hints("αλγοριθμων")
    lines = result.splitlines()
    # At least one line matches "- <something>"
    bullet_lines = [ln for ln in lines if ln.startswith("- ")]
    assert any("αλγορ" in ln for ln in bullet_lines)


def test_university_entity_format() -> None:
    """University entities use the '[University] CANONICAL_LABEL' format."""
    result = build_grounding_hints("ΑΠΘ")
    assert "- [University] ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ" in result


def test_stem_bullet_has_accented_variant() -> None:
    """Stem bullets must show 'plain | accented' to cover mixed-case KG titles.

    The KG stores some titles in ALL-CAPS accent-free ("ΑΛΓΟΡΙΘΜΟΙ") and others
    in mixed-case accented ("Αλγόριθμοι"). SPARQL LCASE() strips case but not
    Unicode accents, so CONTAINS(LCASE("Αλγόριθμοι"), "αλγορ") is false.
    The hint emits both variants so the LLM generates an OR filter.
    """
    result = build_grounding_hints("αλγοριθμων")
    # "αλγορ" has last vowel ο → accented variant "αλγόρ"
    assert "αλγορ | αλγόρ" in result


# ---------------------------------------------------------------------------
# Grounding fix #1 — institution-word disambiguation
# ---------------------------------------------------------------------------


def test_panepistimio_peiraia_resolves_to_university_not_tei() -> None:
    """Explicitly naming 'πανεπιστημιο' must route to ΠΑΝΕΠΙΣΤΗΜΙΟ ΠΕΙΡΑΙΩΣ.

    Root cause of the old bug: 'πανεπιστημιο' was stripped as a topic stopword,
    leaving only the bare 'πειραια' unigram which scores 90 for ΤΕΙ ΠΕΙΡΑΙΑ
    (verbatim substring match) but only 77 for ΠΑΝΕΠΙΣΤΗΜΙΟ ΠΕΙΡΑΙΩΣ.  The fix
    keeps institution words for entity matching so the bigram
    'πανεπιστημιο πειραια' (score 92.7) beats the ΤΕΙ unigram.
    """
    result = build_grounding_hints(
        "Τι συγγράμματα οικονομικών διδάσκονται στο πανεπιστημιο πειραια;"
    )
    assert "ΠΑΝΕΠΙΣΤΗΜΙΟ ΠΕΙΡΑΙΩΣ" in result
    assert "ΤΕΙ ΠΕΙΡΑΙΑ" not in result


def test_panepistimio_peiraia_accented_resolves_to_university_not_tei() -> None:
    """Accented variant 'Πανεπιστήμιο Πειραιά' must also resolve correctly."""
    result = build_grounding_hints(
        "Τι συγγράμματα οικονομικών διδάσκονται στο Πανεπιστήμιο Πειραιά;"
    )
    assert "ΠΑΝΕΠΙΣΤΗΜΙΟ ΠΕΙΡΑΙΩΣ" in result
    assert "ΤΕΙ ΠΕΙΡΑΙΑ" not in result


def test_two_acronyms_both_retained() -> None:
    """Both ΑΠΘ and ΕΚΠΑ must appear — greedy selection must not suppress either.

    Both are acronym unigrams (highest priority).  Non-overlapping spans mean
    both are accepted; no fuzzy bigram should displace them.
    """
    result = build_grounding_hints("ΑΠΘ και ΕΚΠΑ")
    assert "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ" in result
    assert "ΕΘΝΙΚΟ & ΚΑΠΟΔΙΣΤΡΙΑΚΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΑΘΗΝΩΝ" in result


def test_bare_panepistimio_emits_no_university() -> None:
    """A lone 'πανεπιστημιο' with no discriminating city token must emit nothing.

    The glue guard skips all-glue-word windows; the unigram 'πανεπιστημιο' would
    otherwise partial-match every 'ΠΑΝΕΠΙΣΤΗΜΙΟ X' at ~100 and inject a random
    university.
    """
    result = build_grounding_hints("πανεπιστημιο")
    assert "[University]" not in result


# ---------------------------------------------------------------------------
# Class-tagged Resolved title(s) format (dual course/book search) — added for
# book title linking. rank_titles is monkeypatched so these tests exercise
# the FORMATTING and DISAMBIGUATION logic only, independent of entities.db
# contents or real corpus ranking (that's title_index's own test suite).
#
# The question text is a made-up, non-Greek-word phrase so it can't
# accidentally resolve as an entity via the real gazetteer/linker — these
# tests only care about the residual content phrase reaching rank_titles.
# ---------------------------------------------------------------------------

import app.grounding.hints as hints_module  # noqa: E402
from app.grounding.title_index import TitleMatch  # noqa: E402

_NONSENSE_QUESTION = "ζωροβατικη μελετη ξενοφωνικης"


def _course_match(norm="ζωροβατικη μελετη", score=0.9, surfaces=None):
    return TitleMatch(
        normalized_title=norm, score=score,
        surface_forms=surfaces or [f"{norm.upper()}"], entity_class="course",
    )


def _book_match(norm="ξενοφωνικης θεωριας", score=0.9, surfaces=None):
    return TitleMatch(
        normalized_title=norm, score=score,
        surface_forms=surfaces or [f"{norm.upper()}"], entity_class="book",
    )


def test_course_only_match_formats_with_course_tag(monkeypatch) -> None:
    def fake_rank_titles(phrase, k=3, *, entity_class="course"):
        return [_course_match()] if entity_class == "course" else []

    monkeypatch.setattr(hints_module, "rank_titles", fake_rank_titles)
    result = build_grounding_hints(_NONSENSE_QUESTION)

    assert "[Course]" in result
    assert "[Book]" not in result
    assert "matched BOTH" not in result


def test_book_only_match_formats_with_book_tag(monkeypatch) -> None:
    def fake_rank_titles(phrase, k=3, *, entity_class="course"):
        return [_book_match()] if entity_class == "book" else []

    monkeypatch.setattr(hints_module, "rank_titles", fake_rank_titles)
    result = build_grounding_hints(_NONSENSE_QUESTION)

    assert "[Book]" in result
    assert "[Course]" not in result
    assert "matched BOTH" not in result


def test_different_titles_both_classes_no_collision_note(monkeypatch) -> None:
    """Course matches title A, book matches a DIFFERENT title B — both lines
    render, but no note: two different titles matching is not an ambiguity,
    and a note there would be factually false."""

    def fake_rank_titles(phrase, k=3, *, entity_class="course"):
        return [_course_match()] if entity_class == "course" else [_book_match()]

    monkeypatch.setattr(hints_module, "rank_titles", fake_rank_titles)
    result = build_grounding_hints(_NONSENSE_QUESTION)

    assert "[Course]" in result
    assert "[Book]" in result
    assert "matched BOTH" not in result


def test_same_title_both_classes_emits_collision_note(monkeypatch) -> None:
    """The SAME normalized title matching both classes must emit both lines
    AND the collision note, naming the colliding title."""

    def fake_rank_titles(phrase, k=3, *, entity_class="course"):
        norm, surface = "ιδια τιτλος", "ΙΔΙΑ ΤΙΤΛΟΣ"
        if entity_class == "course":
            return [_course_match(norm=norm, surfaces=[surface])]
        return [_book_match(norm=norm, surfaces=[surface])]

    monkeypatch.setattr(hints_module, "rank_titles", fake_rank_titles)
    result = build_grounding_hints(_NONSENSE_QUESTION)

    assert "[Course]" in result
    assert "[Book]" in result
    assert "matched BOTH a Course and a Book" in result
    assert "ΙΔΙΑ ΤΙΤΛΟΣ" in result  # names the colliding title


def test_surface_forms_joined_with_pipe(monkeypatch) -> None:
    def fake_rank_titles(phrase, k=3, *, entity_class="course"):
        if entity_class != "course":
            return []
        return [_course_match(surfaces=["ΑΛΦΑ ΒΗΤΑ", "Άλφα Βήτα"])]

    monkeypatch.setattr(hints_module, "rank_titles", fake_rank_titles)
    result = build_grounding_hints(_NONSENSE_QUESTION)

    assert '"ΑΛΦΑ ΒΗΤΑ" | "Άλφα Βήτα"' in result


def test_book_linking_disabled_suppresses_book_search(monkeypatch) -> None:
    calls: list[str] = []

    def fake_rank_titles(phrase, k=3, *, entity_class="course"):
        calls.append(entity_class)
        return [_course_match()] if entity_class == "course" else [_book_match()]

    monkeypatch.setattr(hints_module, "rank_titles", fake_rank_titles)
    monkeypatch.setattr(hints_module.settings, "book_linking_enabled", False)
    result = build_grounding_hints(_NONSENSE_QUESTION)

    assert "book" not in calls
    assert "course" in calls
    assert "[Book]" not in result


def test_per_class_thresholds_apply_independently(monkeypatch) -> None:
    """A score that clears the book threshold but not the (higher) course
    threshold must be accepted for book and dropped for course."""

    def fake_rank_titles(phrase, k=3, *, entity_class="course"):
        return [_course_match(score=0.75)] if entity_class == "course" else [_book_match(score=0.75)]

    monkeypatch.setattr(hints_module, "rank_titles", fake_rank_titles)
    monkeypatch.setattr(hints_module.settings, "course_match_threshold", 0.8)
    monkeypatch.setattr(hints_module.settings, "book_match_threshold", 0.7)
    result = build_grounding_hints(_NONSENSE_QUESTION)

    assert "[Course]" not in result  # 0.75 < 0.8 course threshold
    assert "[Book]" in result  # 0.75 >= 0.7 book threshold
