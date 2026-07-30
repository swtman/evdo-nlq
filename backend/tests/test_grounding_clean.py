"""Tests for app.grounding.clean — title-corpus cleaning for the entity builder.

All tests are pure-function, no I/O, no live data needed.
Run from backend/: uv run pytest tests/test_grounding_clean.py -v
"""

from app.grounding.clean import clean_titles
from app.grounding.normalize import normalize_greek

# ---------------------------------------------------------------------------
# The bug this module fixes: embedded non-breaking space must survive
# ---------------------------------------------------------------------------


def test_embedded_nbsp_is_preserved_in_surface() -> None:
    """A title with a mid-string NBSP (U+00A0) must be stored byte-identical.

    This is the exact bug found while building book search: the KG stores
    "ΟΙΚΟΝΟΜΕΤΡΙΑ\xa0 ΙΙ" (a non-breaking space before the regular space),
    and the old cleaning code silently rewrote it to "ΟΙΚΟΝΟΜΕΤΡΙΑ ΙΙ" before
    storing it — a different RDF literal, which would bind zero triples.
    """
    raw = "ΟΙΚΟΝΟΜΕΤΡΙΑ\xa0 ΙΙ"
    surface_map, drops = clean_titles([raw])

    assert drops.total == 0
    assert "οικονομετρια ιι" in surface_map
    assert surface_map["οικονομετρια ιι"] == {raw}  # byte-identical, NBSP intact


def test_leading_tab_is_preserved_in_surface() -> None:
    """A leading tab (the original course-corpus dirt) is also preserved raw."""
    raw = "\tΑΝΕΞΑΡΤΗΤΗ ΣΠΟΥΔΗ 2"
    surface_map, drops = clean_titles([raw])

    assert drops.total == 0
    assert surface_map["ανεξαρτητη σπουδη 2"] == {raw}


def test_normal_title_is_unaffected() -> None:
    """A title with no whitespace irregularities round-trips exactly."""
    raw = "Αρχιτεκτονική Υπολογιστών"
    surface_map, drops = clean_titles([raw])

    assert drops.total == 0
    assert surface_map["αρχιτεκτονικη υπολογιστων"] == {raw}


# ---------------------------------------------------------------------------
# Drop reasons — itemized, not a bare total
# ---------------------------------------------------------------------------


def test_mojibake_title_is_dropped_and_counted() -> None:
    raw = "Advances in Alzheimer�s Disease [electronic resource]"
    surface_map, drops = clean_titles([raw])

    assert surface_map == {}
    assert drops.mojibake == 1
    assert drops.empty == 0
    assert drops.newline == 0
    assert drops.total == 1


def test_empty_title_is_dropped_and_counted() -> None:
    surface_map, drops = clean_titles(["", "   ", "\t\t"])

    assert surface_map == {}
    assert drops.empty == 3
    assert drops.total == 3


def test_newline_title_is_dropped_and_counted() -> None:
    """A literal newline would break the one-bullet-per-line hint format
    and the SPARQL string literal syntax — dropped rather than stored."""
    surface_map, drops = clean_titles(["Τίτλος\nΜε Newline", "Τίτλος\rΜε CR"])

    assert surface_map == {}
    assert drops.newline == 2
    assert drops.total == 2


def test_drop_reasons_are_independent_counters() -> None:
    kept_title = "Καλός Τίτλος"
    raw_titles = [
        "",  # empty
        "Τίτλος\nΜε Newline",  # newline
        "Bad�Title",  # mojibake
        kept_title,  # kept
    ]
    surface_map, drops = clean_titles(raw_titles)

    assert drops.empty == 1
    assert drops.newline == 1
    assert drops.mojibake == 1
    assert drops.total == 3
    assert len(surface_map) == 1
    # Derived via normalize_greek rather than hand-typed: Greek final-sigma
    # (ς, U+03C2) and regular sigma (σ, U+03C3) look identical in most fonts,
    # and a hand-typed literal here previously used the wrong one (see
    # test_grounding_normalize.py's header comment for the same warning).
    assert normalize_greek(kept_title) in surface_map


# ---------------------------------------------------------------------------
# Grouping: whitespace-only variants share one norm, both surfaces kept
# ---------------------------------------------------------------------------


def test_whitespace_variants_share_one_norm_both_surfaces_kept() -> None:
    """Two raw titles differing only by an NBSP vs. a regular space normalize
    to the same key but must NOT collapse into one surface form — either
    could be the KG's actual stored literal."""
    variant_nbsp = "ΤΙΤΛΟΣ\xa0ΜΕ ΚΕΝΟ"
    variant_space = "ΤΙΤΛΟΣ ΜΕ ΚΕΝΟ"
    surface_map, drops = clean_titles([variant_nbsp, variant_space])

    assert drops.total == 0
    assert len(surface_map) == 1
    (surfaces,) = surface_map.values()
    assert surfaces == {variant_nbsp, variant_space}


def test_mixed_case_and_all_caps_variants_group_under_one_norm() -> None:
    """Existing behavior preserved: ALL-CAPS accent-free and mixed-case
    accented KG storage variants of the same title share one norm key."""
    surface_map, drops = clean_titles(["ΑΡΧΙΤΕΚΤΟΝΙΚΗ ΥΠΟΛΟΓΙΣΤΩΝ", "Αρχιτεκτονική Υπολογιστών"])

    assert drops.total == 0
    assert len(surface_map) == 1
    (surfaces,) = surface_map.values()
    assert surfaces == {"ΑΡΧΙΤΕΚΤΟΝΙΚΗ ΥΠΟΛΟΓΙΣΤΩΝ", "Αρχιτεκτονική Υπολογιστών"}


# ---------------------------------------------------------------------------
# Class-agnostic: identical behavior regardless of whether titles are
# courses or books — the function has no class-specific logic.
# ---------------------------------------------------------------------------


def test_empty_input_returns_empty_map_and_zero_drops() -> None:
    surface_map, drops = clean_titles([])

    assert surface_map == {}
    assert drops.total == 0
