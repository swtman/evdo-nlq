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

from app.grounding.lexicon import _SEARCH_LOOKALIKES, _SEARCH_SYNONYMS

# Matches a single space followed by a parenthesised annotation at end-of-string.
# The content between the parentheses can be any non-empty sequence of characters
# (typically Greek words and slashes), so the pattern is intentionally broad:
# we only care that it is at the very end of the string.
_STATUS_SUFFIX_RE = re.compile(r" \([^)]+\)$")


def drop_status_suffix(text: str) -> str:
    """Remove ONE trailing " (…)" annotation, keeping case and accents.

    Step 1 of ``normalize_greek``, exposed on its own for display: the
    ΟΝΤΟΛΟΓΙΑ department card is titled by the name its group key stands for
    ("ΝΟΣΗΛΕΥΤΙΚΗΣ" for ΝΟΣΗΛΕΥΤΙΚΗΣ, ΝΟΣΗΛΕΥΤΙΚΗΣ (ΑΛΕΞΑΝΔΡΟΥΠΟΛΗ), …), with
    the exact names listed under it (ADR-029). One definition, so the header
    can never disagree with the key.

    Examples:
        >>> drop_status_suffix("ΠΡΟΓΡΑΜΜΑ ΣΠΟΥΔΩΝ ΝΟΣΗΛΕΥΤΙΚΗΣ (ΛΑΜΙΑ)")
        'ΠΡΟΓΡΑΜΜΑ ΣΠΟΥΔΩΝ ΝΟΣΗΛΕΥΤΙΚΗΣ'
    """
    return _STATUS_SUFFIX_RE.sub("", text)


def normalize_greek(text: str, *, strip_status_suffix: bool = True) -> str:
    """Normalize a Greek string to an accent-free, lowercase, whitespace-collapsed form.

    Applies the five-step pipeline described in the module docstring.

    Args:
        text: A Greek (or mixed Greek/ASCII) string — may be user input or a KG label.
        strip_status_suffix: Step 1 on/off. On (default) for university and
            department names, where a trailing "(…)" is a status or campus
            annotation. ``title_key`` turns it off: in course/book titles the
            trailing parenthetical is meaningful ("(Θ)" vs "(Ε)", "(2nd edition)").

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
    if strip_status_suffix:
        text = drop_status_suffix(text)

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


# ---------------------------------------------------------------------------
# Title keys for course/book (title-linking plan: branch 2b, finding F18, decision C3)
# ---------------------------------------------------------------------------
#
# WHY A SEPARATE KEY FOR TITLES
# The stored search key and the question must be prepared IDENTICALLY, or an
# exactly-typed title does not find itself. Measured before this change (S23):
# course titles with punctuation inside a word were found 48% of the time, titles
# ending in "(…)" 53%. Causes: the question tokenizer splits on punctuation while
# the stored key kept it ("συνολα-ανεξαρτητη"), and normalize_greek strips a
# trailing "(…)" — right for department status notes, wrong for titles, where it
# merged e.g. ΓΕΩΦΥΣΙΚΗ (Θ) with (Ε) and first with revised editions (C3).
#
# title_key   — the full title: accents/case removed, punctuation → space,
#               digits kept, series markers folded. Nothing is deleted:
#               "[electronic resource]" stays as words.
# title_family — the same key without a trailing "(…)" / "[…]": the family that
#               groups a title with its tailed variants, so a question that leaves
#               the tail out still finds all of them (the "optional tail").

# Any run of characters that is not a letter or digit (Unicode-aware). Underscore
# counts as punctuation here although \w matches it.
_NON_WORD_RE = re.compile(r"[\W_]+", flags=re.UNICODE)
# One trailing parenthetical or bracketed tail, with surrounding spaces.
_TRAILING_TAIL_RE = re.compile(r"\s*[\(\[][^\(\)\[\]]*[\)\]]\s*$")


def title_key(text: str) -> str:
    """The course/book search key: same function for stored titles and questions.

    Examples:
        >>> title_key("Μουσικά Σύνολα-Ανεξάρτητη Μελέτη")
        'μουσικα συνολα ανεξαρτητη μελετη'
        >>> title_key("ΓΕΩΦΥΣΙΚΗ  (Θ)")
        'γεωφυσικη θ'
        >>> title_key("Αρχιτεκτονική Υπολογιστών I")
        'αρχιτεκτονικη υπολογιστων ι'
    """
    if not text:
        return ""
    base = normalize_greek(text, strip_status_suffix=False)
    return fold_series_markers(" ".join(_NON_WORD_RE.sub(" ", base).split()))


def title_family(text: str) -> str:
    """``title_key`` of the title without its trailing "(…)"/"[…]" tail(s).

    Falls back to ``title_key(text)`` when nothing would be left (a title that is
    only a parenthetical), so the family key is never empty.

    Examples:
        >>> title_family("ΓΕΩΦΥΣΙΚΗ  (Θ)")
        'γεωφυσικη'
        >>> title_family("ΓΕΡΜΑΝΙΚΑ Ι (2019-2020)")
        'γερμανικα ι'
    """
    stripped = text or ""
    while True:
        shorter = _TRAILING_TAIL_RE.sub("", stripped)
        if shorter == stripped:
            break
        stripped = shorter
    return title_key(stripped) or title_key(text)


# ---------------------------------------------------------------------------
# ΟΝΤΟΛΟΓΙΑ page search — word folding (ADR-030)
# ---------------------------------------------------------------------------
# The page search (title_index/word_search.py) compares WORDS: the words of every exact
# name (index time) with the words typed (search time). Both sides go through
# search_fold, so they agree by construction. Unlike normalize_greek's default, the
# trailing "(…)" is KEPT — campus names such as «(ΛΑΡΙΣΑ)» are what people search for
# (S33/S35). Behaviour pinned to the measured S35 v2.2 prototype (tests/test_search_fold.py).

# Two or more single letters each followed by a dot: «τ.ε.» -> «τε».
_DOTTED_ABBREVIATION_RE = re.compile(r"(?<!\w)((?:[^\W\d_]\.){2,})")
# A search word: a run of letters/digits (punctuation and spaces separate words).
_SEARCH_WORD_RE = re.compile(r"[^\W_]+")


def search_fold(text: str) -> str:
    """Fold a name or a query for the ΟΝΤΟΛΟΓΙΑ word search.

    ``normalize_greek`` with the "(…)" kept, then: dotted abbreviations joined
    («Τ.Ε.» -> «τε»), ``lexicon._SEARCH_SYNONYMS`` («&» -> «και», «θεσ/νικησ» ->
    «θεσσαλονικησ»), and whole-word ``lexicon._SEARCH_LOOKALIKES`` (Latin «te» -> «τε»).

    Examples:
        >>> search_fold("ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ")
        'αριστοτελειο πανεπιστημιο θεσσαλονικησ'
        >>> search_fold("ΜΗΧΑΝΟΛΟΓΩΝ ΜΗΧΑΝΙΚΩΝ Τ.Ε.")
        'μηχανολογων μηχανικων τε'
    """
    folded = normalize_greek(text, strip_status_suffix=False)
    folded = _DOTTED_ABBREVIATION_RE.sub(lambda m: m.group(1).replace(".", "") + " ", folded)
    for written, meant in _SEARCH_SYNONYMS.items():
        folded = folded.replace(written, meant)
    return " ".join(_SEARCH_LOOKALIKES.get(w, w) for w in folded.split())


def search_words(text: str) -> list[str]:
    """The words of ``search_fold(text)``, punctuation dropped.

    Examples:
        >>> search_words("ΝΟΣΗΛΕΥΤΙΚΗΣ (ΛΑΡΙΣΑ)")
        ['νοσηλευτικησ', 'λαρισα']
    """
    return _SEARCH_WORD_RE.findall(search_fold(text))


# ---------------------------------------------------------------------------
# Question word tokens — shared by questions and institution labels (ADR-032)
# ---------------------------------------------------------------------------
#
# WHY HERE
# The words grounding compares with KG names come from a question through
# ``mentions._tokenize``: runs of letters or digits, words shorter than 3
# characters, numbers and stopwords («και», «του», …) dropped. An exact match
# only works if the LABELS are cut into words the same way — before ADR-032 the
# exact index kept «ΚΑΙ», «&», «,» and «/», so «τμημα βιοχημειας και
# βιοτεχνολογιας» could never match ΒΙΟΧΗΜΕΙΑΣ ΚΑΙ ΒΙΟΤΕΧΝΟΛΟΓΙΑΣ exactly (S41).
# Both sides now call these functions: ``mentions._tokenize`` for questions,
# ``gazetteer`` for its token-key indexes. They live in this module because
# ``gazetteer`` cannot import ``mentions`` (mentions → linker → gazetteer).

_WORD_TOKEN_RE = re.compile(r"[^\s\W\d]+|\d+", flags=re.UNICODE)


def word_tokens(text: str) -> list[str]:
    """Runs of letters (no digits, no punctuation) or runs of digits, in order."""
    return _WORD_TOKEN_RE.findall(text)


def is_content_token(token: str, stopwords: frozenset[str]) -> bool:
    """A word grounding keeps: ≥ 3 characters, not a number, not a stopword.

    Args:
        token: One item of ``word_tokens``.
        stopwords: Normalized stopwords (``lexicon._GREEK_STOPWORDS`` or
            ``lexicon._ENTITY_STOPWORDS``).
    """
    return len(token) >= 3 and not token.isdigit() and normalize_greek(token) not in stopwords


def content_tokens(text: str, stopwords: frozenset[str]) -> list[str]:
    """The content words of ``text`` — the tokens ``mentions._tokenize`` keeps.

    Raw tokens (original case kept); callers normalize them as needed.

    Examples:
        >>> from app.grounding.lexicon import _ENTITY_STOPWORDS
        >>> content_tokens("ΒΙΟΧΗΜΕΙΑΣ ΚΑΙ ΒΙΟΤΕΧΝΟΛΟΓΙΑΣ", _ENTITY_STOPWORDS)
        ['ΒΙΟΧΗΜΕΙΑΣ', 'ΒΙΟΤΕΧΝΟΛΟΓΙΑΣ']
    """
    return [tok for tok in word_tokens(text) if is_content_token(tok, stopwords)]
