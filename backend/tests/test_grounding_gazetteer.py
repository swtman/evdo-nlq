"""Tests for app.grounding.gazetteer — entity label store for grounding.

TDD: these tests are written BEFORE the implementation.

The gazetteer loads canonical university and department labels from
scripts/grounding_labels.json, deduplicates them, and builds lookup indices
so that linker.py can resolve user-typed entity mentions to KG labels.

Run from backend/:
    uv run pytest tests/test_grounding_gazetteer.py -v
"""

from __future__ import annotations

from app.grounding.gazetteer import (
    ACRONYM_MAP,
    get_departments,
    get_department_index,
    get_universities,
    get_university_index,
)
from app.grounding.normalize import normalize_greek


# ---------------------------------------------------------------------------
# University count and dedup
# ---------------------------------------------------------------------------


def test_university_count() -> None:
    """Exactly 46 distinct university labels after dedup."""
    assert len(get_universities()) == 46


def test_no_duplicate_universities() -> None:
    """The returned list has no repeated entries."""
    unis = get_universities()
    assert len(unis) == len(set(unis))


def test_apth_in_universities() -> None:
    """Canonical ΑΠΘ label is present in the university list."""
    assert "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ" in get_universities()


def test_all_known_unis_present() -> None:
    """Spot-check a handful of expected university labels."""
    unis = get_universities()
    expected_subset = [
        "ΕΘΝΙΚΟ & ΚΑΠΟΔΙΣΤΡΙΑΚΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΑΘΗΝΩΝ",
        "ΕΘΝΙΚΟ ΜΕΤΣΟΒΙΟ ΠΟΛΥΤΕΧΝΕΙΟ",
        "ΟΙΚΟΝΟΜΙΚΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΑΘΗΝΩΝ",
        "ΠΑΝΕΠΙΣΤΗΜΙΟ ΚΡΗΤΗΣ",
        "ΧΑΡΟΚΟΠΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ",
        "ΑΣΠΑΙΤΕ",
        "ΤΕΙ ΚΡΗΤΗΣ",
        "ΠΟΛΥΤΕΧΝΕΙΟ ΚΡΗΤΗΣ",
    ]
    for label in expected_subset:
        assert label in unis, f"Expected university label missing: {label!r}"


# ---------------------------------------------------------------------------
# Department count and dedup
# ---------------------------------------------------------------------------


def test_department_pair_count() -> None:
    """Exactly 799 distinct (university, department) pairs after dedup."""
    assert len(get_departments()) == 799


def test_no_duplicate_department_pairs() -> None:
    """No two dicts in get_departments() share the same (university, department) pair."""
    depts = get_departments()
    pairs = [(d["university"], d["department"]) for d in depts]
    assert len(pairs) == len(set(pairs))


def test_department_has_university_key() -> None:
    """Every department dict has both 'university' and 'department' string keys."""
    assert all("university" in d and "department" in d for d in get_departments())


def test_department_values_are_strings() -> None:
    """The 'university' and 'department' values are non-empty strings."""
    for d in get_departments():
        assert isinstance(d["university"], str) and d["university"]
        assert isinstance(d["department"], str) and d["department"]


def test_department_universities_are_valid() -> None:
    """Every department's 'university' value is in the canonical university list."""
    valid_unis = set(get_universities())
    for d in get_departments():
        assert d["university"] in valid_unis, (
            f"Department has unknown university: {d['university']!r}"
        )


# ---------------------------------------------------------------------------
# ACRONYM_MAP
# ---------------------------------------------------------------------------


def test_acronym_map_apth() -> None:
    """ΑΠΘ maps to the canonical ΑΠΘ label."""
    assert ACRONYM_MAP["ΑΠΘ"] == "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ"


def test_acronym_map_ekpa() -> None:
    """ΕΚΠΑ maps to the canonical ΕΚΠΑ label."""
    assert ACRONYM_MAP["ΕΚΠΑ"] == "ΕΘΝΙΚΟ & ΚΑΠΟΔΙΣΤΡΙΑΚΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΑΘΗΝΩΝ"


def test_acronym_map_values_are_valid_unis() -> None:
    """Every ACRONYM_MAP value is a canonical university label."""
    valid_unis = set(get_universities())
    for abbrev, full_name in ACRONYM_MAP.items():
        assert full_name in valid_unis, (
            f"ACRONYM_MAP[{abbrev!r}] = {full_name!r} is not in get_universities()"
        )


def test_acronym_map_has_at_least_14_entries() -> None:
    """The map covers the documented set of common Greek university abbreviations."""
    assert len(ACRONYM_MAP) >= 14


# ---------------------------------------------------------------------------
# University index (get_university_index)
# ---------------------------------------------------------------------------


def test_university_index_lookup() -> None:
    """normalize_greek(canonical_label) maps back to the canonical label in the index."""
    index = get_university_index()
    key = normalize_greek("ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ")
    assert key in index
    assert "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ" in index[key]


def test_university_index_covers_all_unis() -> None:
    """Every university's normalized label has an entry in the index."""
    index = get_university_index()
    for uni in get_universities():
        key = normalize_greek(uni)
        assert key in index, f"University missing from index: {uni!r}"
        assert uni in index[key]


def test_university_index_values_are_lists() -> None:
    """All index values are lists of strings."""
    for key, val in get_university_index().items():
        assert isinstance(val, list), f"Index value for {key!r} is not a list"
        assert all(isinstance(s, str) for s in val)


# ---------------------------------------------------------------------------
# Department index (get_department_index)
# ---------------------------------------------------------------------------


def test_dept_index_lookup() -> None:
    """Spot-check: a normalized department name appears in the department index."""
    index = get_department_index()
    # The index has at least one entry
    assert len(index) > 0
    # Every value is a list of dicts with university+department keys
    for key, entries in list(index.items())[:5]:
        assert isinstance(entries, list)
        for entry in entries:
            assert "university" in entry and "department" in entry


def test_dept_index_values_are_lists_of_dicts() -> None:
    """All department index values are lists of dicts."""
    for key, val in get_department_index().items():
        assert isinstance(val, list), f"Index value for {key!r} is not a list"
        for item in val:
            assert isinstance(item, dict)
            assert "university" in item
            assert "department" in item


def test_dept_index_covers_all_depts() -> None:
    """Every department is reachable from the index under its normalized name."""
    index = get_department_index()
    for dept_dict in get_departments():
        # Status-suffix stripping and normalization happens in normalize_greek
        key = normalize_greek(dept_dict["department"])
        assert key in index, f"Department missing from index: {dept_dict['department']!r}"


# ---------------------------------------------------------------------------
# Module-level cache (identity check)
# ---------------------------------------------------------------------------


def test_cache_works_universities() -> None:
    """Two consecutive calls to get_universities() return the SAME object."""
    first = get_universities()
    second = get_universities()
    assert first is second, "get_universities() should return a cached object"


def test_cache_works_departments() -> None:
    """Two consecutive calls to get_departments() return the SAME object."""
    first = get_departments()
    second = get_departments()
    assert first is second, "get_departments() should return a cached object"


def test_cache_works_university_index() -> None:
    """Two consecutive calls to get_university_index() return the SAME object."""
    first = get_university_index()
    second = get_university_index()
    assert first is second


def test_cache_works_department_index() -> None:
    """Two consecutive calls to get_department_index() return the SAME object."""
    first = get_department_index()
    second = get_department_index()
    assert first is second
