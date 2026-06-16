"""Tests for app.grounding.stem — Greek word stemming for SPARQL CONTAINS hints.

All tests are pure-function, no I/O, no fixtures.
Run from backend/: uv run pytest tests/test_grounding_stem.py -v

Design rationale:
    greek_stem() is used to inject a reduced word root into SPARQL
    CONTAINS(LCASE(?label), "stem") filters.  EvdoGraph stores titles in
    ALL-CAPS; Greek inflects heavily; the stem must survive all inflectional
    forms so that a single CONTAINS check matches both nominative and accusative
    plurals, genitive singulars, etc.  Tests cover the canonical cases from the
    algorithm spec plus a selection of edge cases.

NOTE ON SIGMA:
    normalize_greek() (called inside greek_stem) converts both uppercase Σ and
    final-sigma ς to regular σ.  The suffix list uses σ-normalized forms, e.g.
    "ουσ" (not "ους"), "ησ" (not "ης"), "οσ" (not "ος").  Expected values in
    this file are written with regular σ wherever a word-final ς would appear
    in natural Greek spelling.
"""

from app.grounding.stem import MIN_STEM_LEN, greek_stem


# ---------------------------------------------------------------------------
# Required canonical cases from the algorithm specification
# ---------------------------------------------------------------------------


def test_accusative_plural_ους_stem():
    """αλγοριθμους → αλγορ (strip -ουσ then cluster -θμ)."""
    # normalize → "αλγοριθμουσ"; strip "-ουσ" → "αλγοριθμ" (8 chars, ≥4)
    # trailing "θμ" = 2 consonants; vowel before at idx 5 ("ι") → strip → "αλγορ"
    assert greek_stem("αλγοριθμους") == "αλγορ"


def test_nominative_plural_οι_stem():
    """αλγοριθμοι → αλγορ (strip -οι then cluster -θμ)."""
    # normalize → "αλγοριθμοι"; strip "-οι" → "αλγοριθμ" (8 chars)
    # trailing "θμ" → "αλγορ"
    assert greek_stem("αλγοριθμοι") == "αλγορ"


def test_genitive_plural_ων_stem():
    """αλγοριθμων → αλγορ (strip -ων then cluster -θμ)."""
    # normalize → "αλγοριθμων"; strip "-ων" → "αλγοριθμ" (8 chars)
    # trailing "θμ" → "αλγορ"
    assert greek_stem("αλγοριθμων") == "αλγορ"


def test_genitive_singular_ης_stem():
    """πληροφορικης → πληροφορικ (strip -ησ, single trailing consonant → no cluster strip)."""
    # normalize → "πληροφορικησ"; strip "-ησ" → "πληροφορικ" (10 chars)
    # trailing "κ" = 1 consonant → no cluster trim
    assert greek_stem("πληροφορικης") == "πληροφορικ"


def test_genitive_plural_ων_no_cluster():
    """μαθηματικων → μαθηματικ (strip -ων, single trailing consonant)."""
    # normalize → "μαθηματικων"; strip "-ων" → "μαθηματικ" (9 chars)
    # trailing "κ" = 1 consonant → no cluster trim
    assert greek_stem("μαθηματικων") == "μαθηματικ"


def test_genitive_plural_ων_vowel_ending():
    """βιβλιων → βιβλι (strip -ων; result ends in vowel, no cluster)."""
    # normalize → "βιβλιων"; strip "-ων" → "βιβλι" (5 chars, ends in vowel "ι")
    assert greek_stem("βιβλιων") == "βιβλι"


def test_nominative_singular_ος_stem():
    """αλγοριθμος → αλγορ (strip -οσ then cluster -θμ)."""
    # normalize → "αλγοριθμοσ"; strip "-οσ" → "αλγοριθμ" (8 chars)
    # trailing "θμ" → "αλγορ"
    assert greek_stem("αλγοριθμος") == "αλγορ"


def test_empty_string():
    """Empty input → empty output, no exception."""
    assert greek_stem("") == ""


def test_single_char_too_short():
    """Single char word → returned as-is (normalized), no suffix stripping."""
    # normalize("η") → "η" (1 char < MIN_STEM_LEN=4, nothing can strip)
    assert greek_stem("η") == "η"


# ---------------------------------------------------------------------------
# Suffix matching: longer suffix wins over shorter
# ---------------------------------------------------------------------------


def test_longer_suffix_ησεων_wins():
    """ησεων suffix (5 chars) is tried before shorter ησ; longest match wins."""
    # e.g. "συνδρομησεων" → normalize → "συνδρομησεων"
    # try "ησεων" (5): "συνδρομ" (7) → 7 ≥ 4, match! → "συνδρομ"
    # (no trailing consonant cluster, so stop here)
    assert greek_stem("συνδρομησεων") == "συνδρομ"


def test_εων_suffix():
    """εων suffix strips cleanly."""
    # "κλαδεων" → normalize → "κλαδεων"
    # try "ησεων"(5): no match; "ουσ"(3): no; "εων"(3): "κλαδ"(4) ≥ 4 → match
    assert greek_stem("κλαδεων") == "κλαδ"


def test_ου_suffix():
    """ου genitive suffix strips correctly."""
    # "φοιτητου" → normalize → "φοιτητου"
    # "ου" → "φοιτητ" (6) ≥ 4 → match; trailing "τ" = 1 consonant → no cluster
    assert greek_stem("φοιτητου") == "φοιτητ"


# ---------------------------------------------------------------------------
# Accent stripping feeds into suffix matching
# ---------------------------------------------------------------------------


def test_accented_input_normalized_before_stemming():
    """Accents are stripped before suffix matching (normalize is called first)."""
    # "αλγόριθμους" (accented ό) → normalize → "αλγοριθμουσ" → same as unaccented
    assert greek_stem("αλγόριθμους") == "αλγορ"


def test_uppercase_input():
    """ALL-CAPS input (as stored in KG) normalizes and stems correctly."""
    # "ΑΛΓΟΡΙΘΜΟΙ" → normalize → "αλγοριθμοι" → stem → "αλγορ"
    assert greek_stem("ΑΛΓΟΡΙΘΜΟΙ") == "αλγορ"


def test_final_sigma_in_input():
    """Final sigma ς in user input is normalized to σ before suffix matching."""
    # "πληροφορικής" → normalize → "πληροφορικησ" → strip -ησ → "πληροφορικ"
    assert greek_stem("πληροφορικής") == "πληροφορικ"


# ---------------------------------------------------------------------------
# MIN_STEM_LEN guard: suffix only stripped when result >= 4 chars
# ---------------------------------------------------------------------------


def test_suffix_not_stripped_if_would_leave_too_short():
    """If stripping the suffix would leave < MIN_STEM_LEN chars, skip it."""
    # "εσ" has suffix "-εσ"; "ε" is 1 char but MIN_STEM_LEN is 4.
    # No suffix matches and leaves ≥ 4 chars; return normalized form: "εσ"
    # (note: 2 chars, nothing to do)
    result = greek_stem("εσ")
    assert len(result) >= 0  # just mustn't crash; too short to strip anything
    # The key invariant: if a suffix WAS stripped, the result must be ≥ MIN_STEM_LEN
    # We test this via a slightly longer word where the guard fires:
    # "αρεσ" (4 chars) → try "-εσ" (2): would leave "αρ" (2) < 4 → skip
    assert greek_stem("αρεσ") == "αρεσ"


def test_cluster_trim_not_applied_if_would_leave_too_short():
    """Consonant-cluster trim is skipped if the trimmed result would be < MIN_STEM_LEN.

    "αλθμ" (4 chars, 1 leading vowel + 3 trailing consonants):
    - No suffix matches (doesn't end in any listed suffix).
    - Step 3: trailing_consonants=3, cluster_start=1, vowel_pos=0.
    - candidate = stem[:0] = "" → 0 chars < MIN_STEM_LEN=4 → guard fires → no trim.
    - Result: "αλθμ" (the normalized form, unchanged).
    """
    # Only 1 vowel before a 3-consonant cluster → trim would leave "" (< 4) → skipped
    result = greek_stem("αλθμ")
    assert result == "αλθμ"
    assert len(result) >= MIN_STEM_LEN  # stem never shortened below threshold


# ---------------------------------------------------------------------------
# No-suffix words (the stem IS the whole word)
# ---------------------------------------------------------------------------


def test_no_suffix_match_returns_normalized():
    """A word that matches no suffix is returned normalized (accents/case stripped)."""
    # "ΦΥΣΙΚΗ" → normalize → "φυσικη" → no suffix from list matches (ends in "η" which
    # is a vowel; "ησ", "εσ", etc. don't match) → return "φυσικη"
    # Actually "η" doesn't appear in the suffix list, so no match → "φυσικη"
    assert greek_stem("ΦΥΣΙΚΗ") == "φυσικη"


def test_word_already_a_stem():
    """A root-form word with no recognisable suffix passes through unchanged (normalized)."""
    # "λεξη" → normalize → "λεξη"; no suffix matches → "λεξη"
    assert greek_stem("λεξη") == "λεξη"


# ---------------------------------------------------------------------------
# Constant export
# ---------------------------------------------------------------------------


def test_min_stem_len_is_4():
    """MIN_STEM_LEN is the documented value of 4."""
    assert MIN_STEM_LEN == 4
