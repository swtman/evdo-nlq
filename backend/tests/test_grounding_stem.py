"""Tests for app.grounding.stem — Greek word stemming.

All tests are pure-function, no I/O, no fixtures.
Run from backend/: uv run pytest tests/test_grounding_stem.py -v

Two stemmers, two jobs (ADR-031):
    topic_stem() + stem_pattern() build the Topic-stems hint: a Snowball stem
    and a regex with one vowel class per vowel, used by the LLM in
    FILTER(REGEX(LCASE(?title), "pattern")). Tested at the end of this file.
    greek_stem() (the hand-written suffix stemmer below) now only builds the
    FTS5 prefix terms that fetch course/book title CANDIDATES; it stays until
    that swap can be measured with the title eval set (branch 4, user decision Q2).

NOTE ON SIGMA:
    normalize_greek() (called inside greek_stem) converts both uppercase Σ and
    final-sigma ς to regular σ.  The suffix list uses σ-normalized forms, e.g.
    "ουσ" (not "ους"), "ησ" (not "ης"), "οσ" (not "ος").  Expected values in
    this file are written with regular σ wherever a word-final ς would appear
    in natural Greek spelling.
"""

import re

import pytest

from app.grounding.stem import MIN_STEM_LEN, greek_stem, stem_pattern, topic_stem
from app.grounding.title_index.search import _fts_query_terms


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


# ---------------------------------------------------------------------------
# topic_stem — Snowball, with greek_stem as the fallback for too-short stems
# (ADR-031; stemmer choice S39, fallback S40c)
# ---------------------------------------------------------------------------


def test_topic_stem_groups_all_forms_of_a_word():
    """Every form of αλγόριθμος gets ONE stem — accents and case do not matter."""
    forms = ["αλγοριθμων", "αλγορίθμους", "ΑΛΓΟΡΙΘΜΟΙ", "Αλγόριθμοι"]
    assert {topic_stem(f) for f in forms} == {"αλγοριθμ"}


def test_topic_stem_strips_a_nominative_ending():
    """«αναλυση» gets a real stem — greek_stem left it unchanged and the hint
    then dropped it (bug F2)."""
    assert topic_stem("αναλυση") == "αναλυσ"
    assert topic_stem("αναλύσεις") == "αναλυσ"


def test_topic_stem_keeps_a_word_family_apart():
    """θρησκευτικά → θρησκευτ (not θρησκ): Snowball is adopted as-is, it does not
    merge θρησκεία into θρησκευτικός (title-linking plan, decision 7)."""
    assert topic_stem("θρησκευτικα") == "θρησκευτ"


def test_topic_stem_falls_back_when_snowball_cuts_too_short():
    """Snowball gives «θεμ» / «σημ» (< MIN_STEM_LEN), which the hint would drop; the
    fallback keeps greek_stem's longer stem instead (S40c: F1 0.851 → 0.877)."""
    assert topic_stem("θεματα") == "θεματα"
    assert topic_stem("σηματων") == "σηματ"


def test_topic_stem_leaves_latin_words_alone():
    assert topic_stem("python") == "python"


def test_topic_stem_empty():
    assert topic_stem("") == ""


# ---------------------------------------------------------------------------
# stem_pattern — one character class per vowel, so ONE regex matches the
# accent-free ALL-CAPS and the accented mixed-case KG titles (decision C5)
# ---------------------------------------------------------------------------


def test_stem_pattern_vowel_classes():
    assert stem_pattern("αλγοριθμ") == "[αά]λγ[οό]ρ[ιίϊΐ]θμ"


def test_stem_pattern_sigma_matches_final_form():
    """GraphDB's LCASE writes a word-final Σ as ς (S40a), so σ must match both."""
    assert stem_pattern("αναλυσ") == "[αά]ν[αά]λ[υύϋΰ][σς]"


def test_stem_pattern_matches_every_storage_form():
    """Python's str.lower() also writes a final ς — a faithful proxy for LCASE."""
    pattern = stem_pattern(topic_stem("αλγορίθμων"))
    for title in ("ΑΛΓΟΡΙΘΜΟΙ ΚΑΙ ΔΟΜΕΣ", "Αλγόριθμοι και Δομές", "Θεωρία Αλγορίθμων"):
        assert re.search(pattern, title.lower()), title


def test_stem_pattern_whole_word_stem_ending_in_sigma():
    """A stem that IS a whole word ending in σ must still match the title word,
    whose LCASE ends in ς."""
    assert re.search(stem_pattern("θεσμοσ"), "ΘΕΣΜΟΣ".lower())


def test_stem_pattern_latin_unchanged():
    assert stem_pattern("python") == "python"


def test_stem_pattern_rejects_non_letters():
    """Stems are letters only; anything else could be a regex metacharacter."""
    with pytest.raises(ValueError):
        stem_pattern("αλγ.*")


# ---------------------------------------------------------------------------
# The title-candidate search keeps greek_stem (user decision Q2, branch 4)
# ---------------------------------------------------------------------------


def test_fts_candidate_terms_still_use_greek_stem():
    """Swapping these terms changes which course/book titles are ranked; that is
    measured later with the title eval set, not in this branch."""
    assert _fts_query_terms("αλγοριθμων") == ["αλγορ"]
