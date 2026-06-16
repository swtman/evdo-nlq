"""Greek text normalization for the grounding module.

The grounding pipeline must compare user-typed Greek against KG labels that are
stored as ALL-CAPS, accent-free strings — often with trailing status annotations
like "(ΚΑΤΑΡΓΗΘΗΚΕ/ΜΕΤΑΦΕΡΘΗΚΕ)" that users never type.  ``normalize_greek``
reduces both sides to the same canonical form so that string-equality and
fuzzy-match comparisons work correctly regardless of how the input was typed or
how the KG stored it.

Normalization pipeline (applied in order):
    1. Strip trailing parenthetical status suffixes (KG artifact — see WHY below).
    2. NFD-decompose so that combining diacritics (τόνοι) are separate code points.
    3. Drop all "Mn" (Mark, Nonspacing) code points — removes all Greek tone marks.
    4. casefold() — maps Σ → σ, final-sigma ς → σ, uppercase Greek → lowercase.
    5. Collapse whitespace — strip edges, collapse internal runs to a single space.

WHY status-suffix stripping?
    EvdoGraph stores abolished or merged departments with parenthetical annotations,
    e.g. "ΑΙΣΘΗΤΙΚΗΣ ΚΑΙ ΚΟΣΜΗΤΟΛΟΓΙΑΣ (ΚΑΤΑΡΓΗΘΗΚΕ/ΜΕΤΑΦΕΡΘΗΚΕ)".  Users never
    include "(ΚΑΤΑΡΓΗΘΗΚΕ)" in their queries.  Stripping the suffix before comparison
    lets us match abolished department labels the same way as active ones.
"""

import re
import unicodedata

# Matches a single space followed by a parenthesised annotation at end-of-string.
# The content between the parens can be any non-empty sequence of characters
# (typically Greek words and slashes), so the pattern is intentionally broad:
# we only care that it is at the very end of the string.
_STATUS_SUFFIX_RE = re.compile(r" \([^)]+\)$")


def normalize_greek(text: str) -> str:
    """Normalize a Greek string to an accent-free, lowercase, whitespace-collapsed form.

    Applies the five-step pipeline described in the module docstring.  The function
    is pure — it has no side effects, performs no I/O, and returns an empty string
    unchanged.

    Args:
        text: A Greek (or mixed Greek/ASCII) string — may be user input or a KG label.

    Returns:
        The normalized form, suitable for label matching against other normalized strings.

    Examples:
        >>> normalize_greek("αριστοτελείου")
        'αριστοτελειου'
        >>> normalize_greek("ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ")
        'αριστοτελειο πανεπιστημιο θεσ/νικης'
        >>> normalize_greek("ΑΙΣΘΗΤΙΚΗΣ ΚΑΙ ΚΟΣΜΗΤΟΛΟΓΙΑΣ (ΚΑΤΑΡΓΗΘΗΚΕ/ΜΕΤΑΦΕΡΘΗΚΕ)")
        'αισθητικης και κοσμητολογιας'
        >>> normalize_greek("")
        ''
    """
    if not text:
        return ""

    # Step 1 — strip trailing parenthetical status suffix (KG artifact).
    text = _STATUS_SUFFIX_RE.sub("", text)

    # Step 2 — NFD decomposition so combining diacritics become separate code points.
    text = unicodedata.normalize("NFD", text)

    # Step 3 — drop all combining (nonspacing mark) code points, i.e. accent marks.
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")

    # Step 4 — casefold: Σ → σ, ς → σ, uppercase Greek → lowercase Greek.
    text = text.casefold()

    # Step 5 — collapse whitespace: strip edges, squash internal runs to one space.
    text = " ".join(text.split())

    return text
