"""Tests for app.grounding.linker — entity mention resolver.

The linker resolves a user-typed mention (Greek university or department name,
possibly abbreviated or inflected) to a canonical KG label via three strategies:
    1. Acronym lookup  (ΑΠΘ → ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ)
    2. Exact normalized match
    3. Fuzzy match with rapidfuzz (score ≥ FUZZY_THRESHOLD)

All tests here are pure-unit (no network, no file I/O beyond the cached
gazetteer JSON that the grounding module already loads from scripts/).
"""

import pytest

from app.grounding.linker import FUZZY_THRESHOLD, ResolvedEntity, resolve_mention


# ---------------------------------------------------------------------------
# Acronym resolution
# ---------------------------------------------------------------------------


def test_apth_acronym_resolves() -> None:
    """ΑΠΘ must resolve via the ACRONYM_MAP to the canonical AUTh label."""
    results = resolve_mention("ΑΠΘ")
    assert len(results) >= 1
    assert results[0].canonical_label == "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ"
    assert results[0].match_method == "acronym"
    assert results[0].score == 1.0
    assert results[0].entity_type == "university"
    assert results[0].parent_university is None


def test_apth_lowercase_acronym() -> None:
    """Lower-case acronym 'απθ' must still resolve via acronym (normalize handles case)."""
    results = resolve_mention("απθ")
    assert any(r.canonical_label == "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ" for r in results)
    assert any(r.match_method == "acronym" for r in results)


def test_ekpa_acronym_resolves() -> None:
    """ΕΚΠΑ must resolve to the canonical EKPA label."""
    results = resolve_mention("ΕΚΠΑ")
    assert len(results) >= 1
    assert results[0].canonical_label == "ΕΘΝΙΚΟ & ΚΑΠΟΔΙΣΤΡΙΑΚΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΑΘΗΝΩΝ"
    assert results[0].match_method == "acronym"


# ---------------------------------------------------------------------------
# Exact normalized match
# ---------------------------------------------------------------------------


def test_exact_university_match() -> None:
    """The full canonical label (all-caps) must resolve via exact normalized match.

    The canonical label "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ" normalizes to a
    key that hits the university index directly.  The stage-2 exact path must fire
    (it is not an ACRONYM_MAP key, so stage 1 cannot satisfy this assertion).
    """
    results = resolve_mention("ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ")
    assert any(r.entity_type == "university" for r in results)
    uni_results = [r for r in results if r.entity_type == "university"]
    assert uni_results[0].canonical_label == "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ"
    # Assert stage-2 exact match fires — the canonical label is NOT an acronym key
    assert any(r.match_method == "exact" for r in results)


def test_exact_match_score_is_1() -> None:
    """Exact matches must always carry score=1.0."""
    results = resolve_mention("ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ")
    exact = [r for r in results if r.match_method == "exact"]
    if exact:
        assert all(r.score == 1.0 for r in exact)


# ---------------------------------------------------------------------------
# Fuzzy match
# ---------------------------------------------------------------------------


def test_fuzzy_inflected_university() -> None:
    """'αριστοτελειου' (genitive, user-typed) must fuzzy-resolve to AUTh."""
    results = resolve_mention("αριστοτελειου")
    assert len(results) >= 1, "Expected at least one fuzzy result for 'αριστοτελειου'"
    assert any("ΑΡΙΣΤΟΤΕΛ" in r.canonical_label for r in results)
    assert any(r.match_method == "fuzzy" for r in results)


def test_fuzzy_score_above_threshold() -> None:
    """All fuzzy results must have score >= FUZZY_THRESHOLD."""
    results = resolve_mention("αριστοτελειου")
    fuzzy_results = [r for r in results if r.match_method == "fuzzy"]
    assert all(r.score >= FUZZY_THRESHOLD for r in fuzzy_results)


def test_fuzzy_below_threshold_not_returned() -> None:
    """Strings that cannot match any entity above threshold return empty list."""
    results = resolve_mention("xyzfoobar123")
    assert results == []


# ---------------------------------------------------------------------------
# Department with parent
# ---------------------------------------------------------------------------


def test_department_match_includes_parent_university() -> None:
    """Department matches must always carry a non-None parent_university."""
    results = resolve_mention("ΠΛΗΡΟΦΟΡΙΚΗΣ")
    dept_results = [r for r in results if r.entity_type == "department"]
    assert len(dept_results) >= 1, "Expected at least one department result for 'ΠΛΗΡΟΦΟΡΙΚΗΣ'"
    assert all(r.parent_university is not None for r in dept_results)


def test_department_entity_type() -> None:
    """Department matches must have entity_type='department'."""
    results = resolve_mention("ΠΛΗΡΟΦΟΡΙΚΗΣ")
    dept_results = [r for r in results if r.entity_type == "department"]
    assert len(dept_results) >= 1
    assert all(r.entity_type == "department" for r in dept_results)


# ---------------------------------------------------------------------------
# Edge cases / empty / unrecognized
# ---------------------------------------------------------------------------


def test_empty_input_returns_empty() -> None:
    """Empty string must return an empty list (no crash)."""
    assert resolve_mention("") == []


def test_unrecognized_mention_returns_empty() -> None:
    """Completely random ASCII must return an empty list."""
    assert resolve_mention("xyzfoobar123") == []


def test_whitespace_only_returns_empty() -> None:
    """Whitespace-only input normalizes to '' and must return an empty list."""
    assert resolve_mention("   ") == []


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def test_results_deduplicated() -> None:
    """The same canonical_label must appear at most once in the result list."""
    results = resolve_mention("ΑΠΘ")
    labels = [r.canonical_label for r in results]
    assert len(labels) == len(set(labels)), f"Duplicate labels found: {labels}"


def test_results_deduplicated_fuzzy() -> None:
    """Fuzzy results (potentially from both uni + dept index) must be deduplicated."""
    results = resolve_mention("αριστοτελειου")
    labels = [r.canonical_label for r in results]
    assert len(labels) == len(set(labels)), f"Duplicate labels found: {labels}"


# ---------------------------------------------------------------------------
# ResolvedEntity shape
# ---------------------------------------------------------------------------


def test_resolved_entity_is_frozen_dataclass() -> None:
    """ResolvedEntity must be a frozen dataclass (hashable, immutable)."""
    entity = ResolvedEntity(
        canonical_label="TEST",
        entity_type="university",
        parent_university=None,
        match_method="exact",
        score=1.0,
    )
    assert entity.canonical_label == "TEST"
    with pytest.raises(Exception):  # frozen → AttributeError on assignment
        entity.canonical_label = "OTHER"  # type: ignore[misc]


def test_fuzzy_threshold_constant() -> None:
    """FUZZY_THRESHOLD must be a float and within a sensible range."""
    assert isinstance(FUZZY_THRESHOLD, float)
    assert 50.0 <= FUZZY_THRESHOLD <= 100.0
