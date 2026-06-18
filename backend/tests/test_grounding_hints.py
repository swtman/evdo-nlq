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
