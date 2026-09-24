"""Greek text normalization for the grounding module.

The grounding pipeline must compare user-typed Greek against KG labels that are
sometimes (e.g for University and Department labels) stored as ALL-CAPS, 
accent-free strings — often with trailing status annotations
like "(ΚΑΤΑΡΓΗΘΗΚΕ/ΜΕΤΑΦΕΡΘΗΚΕ)".  This normalization function
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
# The content between the parentheses can be any non-empty sequence of characters
# (typically Greek words and slashes), so the pattern is intentionally broad:
# we only care that it is at the very end of the string.
_STATUS_SUFFIX_RE = re.compile(r" \([^)]+\)$")


def normalize_greek(text: str) -> str:
    """Normalize a Greek string to an accent-free, lowercase, whitespace-collapsed form.

    Applies the five-step pipeline described in the module docstring.

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


# ---------------------------------------------------------------------------
# Series markers (title-linking plan, decision 4)
# ---------------------------------------------------------------------------
#
# Course/book titles are often numbered: "ΦΥΣΙΚΗ Ι", "ΦΥΣΙΚΗ ΙΙ", "ΜΑΘΗΜΑΤΙΚΑ 2",
# "ΜΑΘΗΜΑΤΙΚΑ Α". Measured on entities.db (S09): among course titles 6,750 end in
# a Greek roman numeral, 2,637 in a LATIN roman numeral, 1,319 in a digit and 328
# in a single letter. The same numeral is typed both ways — Latin "I" and Greek
# "Ι" look identical but are different characters — so both sides of every
# comparison must be folded to one spelling.

# Latin letters that have a Greek look-alike used in roman numerals. "v" has no
# Greek look-alike and stays Latin ("ΙV" is typically Greek Ι + Latin V).
_LATIN_TO_GREEK_ROMAN = str.maketrans({"i": "ι", "x": "χ"})

# A roman-numeral token after folding: only ι / v / χ, at most 4 characters
# (Ι … ΙΙΙΙ, ΙV, VΙΙΙ, ΧΙ …). Longer runs are not plausible series numbers.
_ROMAN_RE = re.compile(r"^[ιvχ]{1,4}$")
# A numeric series marker: 1-2 digits. Years ("2022") and Eudoxus book codes
# ("94700120") appear in questions constantly and must NOT count as markers.
_DIGIT_RE = re.compile(r"^\d{1,2}$")
# Single-letter series markers ("ΜΑΘΗΜΑΤΙΚΑ Α"): only the first four letters.
_LETTER_MARKERS = frozenset("αβγδ")


def _fold_token(token: str) -> str:
    """Fold one already-normalized token to Greek roman letters if it is roman-only."""
    # Latin i, v, x plus their Greek look-alikes ι, χ (Greek ν is NOT a look-alike of v).
    if token and len(token) <= 4 and all(ch in "ivxιχ" for ch in token):
        return token.translate(_LATIN_TO_GREEK_ROMAN)
    return token


def fold_series_markers(text: str) -> str:
    """Fold Latin roman-numeral tokens to their Greek look-alikes (i→ι, x→χ).

    Applied token by token to an already ``normalize_greek``-ed string, and only
    to tokens made entirely of roman-numeral letters — ordinary words are never
    touched ("introduction" stays as is). Used on BOTH sides of a title
    comparison, so "φυσικη ii" (Latin) and "φυσικη ιι" (Greek) become equal.

    Examples:
        >>> fold_series_markers("φυσικη ii")
        'φυσικη ιι'
        >>> fold_series_markers("φυσικη iv")
        'φυσικη ιv'
    """
    if not text:
        return text
    return " ".join(_fold_token(t) for t in text.split(" "))


def is_series_marker(token: str) -> bool:
    """Whether a normalized token is a series marker (Ι/ΙΙ/I/IV…, 1-2 digits, α-δ).

    Args:
        token: A single token, already passed through ``normalize_greek``.

    Returns:
        True for roman numerals (Greek or Latin letters, ≤ 4 characters),
        1-2 digit numbers, and the single letters α β γ δ; False otherwise —
        in particular for years and book codes.
    """
    if not token:
        return False
    folded = _fold_token(token)
    return bool(_ROMAN_RE.match(folded) or _DIGIT_RE.match(token) or token in _LETTER_MARKERS)
