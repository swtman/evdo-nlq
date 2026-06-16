"""Tests for app.grounding.normalize — Greek text normalization.

All tests are pure-function, no I/O, no fixtures needed.
Run from backend/: uv run pytest tests/test_grounding_normalize.py -v

NOTE ON SIGMA:
    Python's str.casefold() converts both uppercase Σ (U+03A3) and final-sigma
    ς (U+03C2) to regular sigma σ (U+03C3).  Expected values in this file use
    Unicode escape sequences for Greek to avoid editor/encoding confusion about
    which sigma variant is present.
"""

from app.grounding.normalize import normalize_greek

# Aliases for readability in assertion comments (U+03C3 = σ, U+03C2 = ς)
_SIGMA = "σ"  # regular sigma — what casefold() produces
_FINAL_SIGMA = "ς"  # final sigma — what word-final ς looks like before casefold


# ---------------------------------------------------------------------------
# Accent stripping
# ---------------------------------------------------------------------------


def test_accent_stripping_user_input():
    """User-typed accented word loses its tone marks."""
    # "αριστοτελείου" → "αριστοτελειου" (all σ, no accents)
    expected = "αριστοτελειου"
    assert normalize_greek("αριστοτελείου") == expected


def test_accent_stripping_kg_label_with_slash():
    """KG ALL-CAPS label is lowercased and tone-stripped; slash is preserved."""
    # "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ" → "αριστοτελειο πανεπιστημιο θεσ/νικης"
    # NOTE: ΗΣ at word-end → ης with regular sigma (U+03C3).  ΗΣ uses uppercase
    # Σ (U+03A3, medial sigma), not final-sigma ς (U+03C2).  casefold() maps
    # uppercase Σ → σ, so the result is the same regular sigma σ.
    expected = (
        "αριστοτελειο"
        " πανεπιστημιο"
        " θεσ/νικησ"
    )
    assert normalize_greek("ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ") == expected


def test_accent_stripping_mixed_case():
    """Mixed-case accented input is fully normalized."""
    # "Αριστοτέλειο" → "αριστοτελειο"
    expected = "αριστοτελειο"
    assert normalize_greek("Αριστοτέλειο") == expected


# ---------------------------------------------------------------------------
# Final-sigma and sigma normalisation
# ---------------------------------------------------------------------------


def test_final_sigma_becomes_regular_sigma():
    """Greek word ending in ς (U+03C2, final sigma) casefolds to σ (U+03C3).

    casefold() maps ς → σ so that "λογισμός" and "ΛΟΓΙΣΜΟΣ" normalize identically.
    """
    # "λογισμός" → strip accent on ό → "λογισμος" → casefold ς → "λογισμοσ"
    # But ALL the sigmas here are medial except the last character which is ς
    # casefold turns ALL sigma variants to 0x3c3
    result = normalize_greek("λογισμός")
    assert result == "λογισμοσ"
    assert result[-1] == _SIGMA, "final ς must become regular σ after casefold"
    assert result[-1] != _FINAL_SIGMA


def test_regular_sigma_unchanged():
    """Medial σ stays σ after casefold; Σ uppercase casefolds to σ."""
    # "ΣΕΣΣΙΟΝ" → "σεσσιον"
    expected = "σεσσιον"
    assert normalize_greek("ΣΕΣΣΙΟΝ") == expected


# ---------------------------------------------------------------------------
# Status-suffix stripping
# ---------------------------------------------------------------------------


def test_suffix_strip_double_slash_form():
    """Parenthetical ΚΑΤΑΡΓΗΘΗΚΕ/ΜΕΤΑΦΕΡΘΗΚΕ suffix is removed."""
    result = normalize_greek("ΑΙΣΘΗΤΙΚΗΣ ΚΑΙ ΚΟΣΜΗΤΟΛΟΓΙΑΣ (ΚΑΤΑΡΓΗΘΗΚΕ/ΜΕΤΑΦΕΡΘΗΚΕ)")
    # Expected: "αισθητικης και κοσμητολογιας" (with regular sigma at end)
    expected = (
        "αισθητικησ"
        " και"
        " κοσμητολογιασ"
    )
    assert result == expected


def test_suffix_strip_single_word_form():
    """Parenthetical Greek word suffix (Συγχωνεύτηκε) is removed."""
    result = normalize_greek("ΛΟΓΙΣΤΙΚΗΣ ΚΑΙ ΧΡΗΜΑΤΟΟΙΚΟΝΟΜΙΚΗΣ (Συγχωνεύτηκε)")
    # Expected: "λογιστικης και χρηματοοικονομικης"
    expected = (
        "λογιστικησ"
        " και"
        " χρηματοοικονομικησ"
    )
    assert result == expected


def test_suffix_strip_only_at_end():
    """A parenthetical in the middle of a string is NOT stripped."""
    # The regex is anchored to end-of-string, so mid-string parens survive.
    result = normalize_greek("ΤΜΗΜΑ (ΠΑΛΑΙΟ) ΟΝΟΜΑ")
    expected = "τμημα (παλαιο) ονομα"
    assert result == expected


def test_suffix_strip_preserves_normal_names():
    """A label without a status suffix is unchanged (modulo normalisation)."""
    # "ΠΛΗΡΟΦΟΡΙΚΗΣ" → "πληροφορικης" (regular sigma at end)
    expected = "πληροφορικησ"
    assert normalize_greek("ΠΛΗΡΟΦΟΡΙΚΗΣ") == expected


# ---------------------------------------------------------------------------
# Whitespace normalisation
# ---------------------------------------------------------------------------


def test_whitespace_leading_trailing_stripped():
    """Leading and trailing whitespace is removed."""
    expected = "αριστοτελειο"
    assert normalize_greek("  ΑΡΙΣΤΟΤΕΛΕΙΟ  ") == expected


def test_whitespace_internal_runs_collapsed():
    """Multiple consecutive spaces between words collapse to one."""
    expected = (
        "αριστοτελειο"
        " πανεπιστημιο"
    )
    assert normalize_greek("  ΑΡΙΣΤΟΤΕΛΕΙΟ  ΠΑΝΕΠΙΣΤΗΜΙΟ  ") == expected


def test_whitespace_tab_and_newline_collapsed():
    """Tabs and newlines are treated as whitespace and collapsed."""
    expected = (
        "αριστοτελειο"
        " πανεπιστημιο"
    )
    assert normalize_greek("ΑΡΙΣΤΟΤΕΛΕΙΟ\t\nΠΑΝΕΠΙΣΤΗΜΙΟ") == expected


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_string_returns_empty():
    """Empty string input → empty string output (no exceptions)."""
    assert normalize_greek("") == ""


def test_ascii_slash_survives():
    """Non-Greek ASCII characters like '/' are left intact."""
    # "ΘΕΣ/ΝΙΚΗΣ" → "θεσ/νικης"
    expected = "θεσ/νικησ"
    assert normalize_greek("ΘΕΣ/ΝΙΚΗΣ") == expected


def test_already_normalised_is_idempotent():
    """Calling normalize_greek on an already-normalised string is a no-op."""
    first = normalize_greek("ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ")
    second = normalize_greek(first)
    assert first == second
