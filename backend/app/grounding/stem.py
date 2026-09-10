"""Greek word stemming for SPARQL CONTAINS query hints.

The EvdoGraph KG stores book and course titles in different formats 
(sometimes ALL-CAPS and accent-free strings and sometimes mixed-case with accents),
but always in their canonical, uninflected form e.g. 
Users type inflected Greek words e.g. "αλγοριθμους" (accusative plural).  
Because Greek inflects heavily, the exact user form almost never appears 
verbatim in the title.

``greek_stem`` reduces a user-typed word to a short invariant root that appears
across all its inflectional forms.  The root is injected into a SPARQL filter:

    FILTER(CONTAINS(LCASE(?title), "αλγορ"))

Algorithm (three steps):
  1. Normalize — call ``normalize_greek`` to strip accents, casefold ς→σ,
     strip parenthetical status suffixes, collapse whitespace.
  2. Suffix stripping — try each entry in ``_SUFFIXES`` from longest to
     shortest.  Use the first suffix whose removal leaves ≥ ``MIN_STEM_LEN``
     characters.
  3. Consonant-cluster trimming — if the stem after step 2 ends in ≥ 2
     consecutive consonants, find the vowel just before the cluster and strip
     everything from there onward, provided the result is still ≥ ``MIN_STEM_LEN``.

WHY this heuristic over a full morphological analyser?
    A full morphological analyser (e.g. GreekStemmer, spaCy el_core_news_sm)
    adds a non-trivial dependency for a thesis project on a tight budget, and it
    doesn't solve the KG-specific challenge (ALL-CAPS, accent-free, unusual
    domain vocabulary).  The hand-crafted suffix list covers the most common
    Greek inflectional endings that appear in academic/administrative titles and
    is accurate enough for CONTAINS hints — the LLM downstream refines the query.
"""

from app.grounding.normalize import normalize_greek

# Minimum number of characters a stem must have after any stripping step.
# Stems shorter than this would generate too many false positives in CONTAINS.
MIN_STEM_LEN: int = 4

# Greek vowels in their accent-free, lowercase forms (after normalize_greek).
# Used to detect consonant clusters at the end of a stem.
_GREEK_VOWELS: frozenset[str] = frozenset("αεηιουω")

# Ordered list of suffixes to try.  All entries are written in normalized form
# (accent-free, lowercase, ς→σ applied) because they are matched AFTER
# normalize_greek has been called.  The list is ordered longest-first so that
# longer suffixes are preferred over shorter overlapping ones (e.g. "ησεων"
# before "ησ").
_SUFFIXES: tuple[str, ...] = (
    "ησεων",  # 5: gen pl of -ησεις/-ησεων nouns  (e.g. αισθήσεων)
    "ουσ",    # 3: acc pl -ους  (ους → ουσ after ς→σ normalisation)
    "εων",    # 3: gen pl -εων  (e.g. κλάδων/εων forms)
    "ησ",     # 2: gen sg -ης   (ης → ησ after ς→σ)
    "οσ",     # 2: nom sg -ος   (ος → οσ after ς→σ)
    "εσ",     # 2: nom pl -ες   (ες → εσ after ς→σ)
    "ων",     # 2: gen pl -ων
    "οι",     # 2: nom pl -οι
    "ου",     # 2: gen sg -ου   (masc/neuter 2nd decl, e.g. φοιτητού)
    "ει",     # 2: dat sg or other vocalic forms
)


def greek_stem(word: str) -> str:
    """Produce a SPARQL-friendly stem from an inflected Greek word.

    The stem is intended for use in SPARQL CONTAINS filters like:
        FILTER(CONTAINS(LCASE(?title), "stem"))

    The function is pure — no I/O, no side effects, deterministic.

    Args:
        word: An inflected Greek word, possibly with accents and mixed case.
              May also be an ALL-CAPS KG label excerpt.  Multi-word strings are
              accepted but the suffix/cluster logic treats them as one token
              (suited for single-word grounding hints).

    Returns:
        An accent-free, lowercase stem of at least ``MIN_STEM_LEN`` characters,
        or the full normalized form if no stripping was possible (including the
        empty string for empty input).

    Examples:
        >>> greek_stem("αλγοριθμους")
        'αλγορ'
        >>> greek_stem("πληροφορικης")
        'πληροφορικ'
        >>> greek_stem("βιβλιων")
        'βιβλι'
        >>> greek_stem("")
        ''
    """
    # Step 0 — guard: normalize handles empty string already, but return early
    # to avoid unnecessary work.
    if not word:
        return ""

    # Step 1 — normalize: accent-free, lowercase, ς→σ, status suffixes gone.
    normalized = normalize_greek(word)

    if not normalized:
        return ""

    # Step 2 — suffix stripping: try each suffix in order (longest first).
    # Accept the first match that leaves at least MIN_STEM_LEN chars.
    stem = normalized
    for suffix in _SUFFIXES:
        if stem.endswith(suffix):
            candidate = stem[: len(stem) - len(suffix)]
            if len(candidate) >= MIN_STEM_LEN:
                stem = candidate
                break  # longest-first guarantees this is the best match

    # Step 3 — consonant-cluster trimming.
    # Find how many trailing characters are consonants ( not in _GREEK_VOWELS).
    # If there are ≥ 2 trailing consonants, the cluster obscures the readable
    # root; trim back to the vowel that precedes the cluster.
    trailing_consonants = 0
    for ch in reversed(stem):
        if ch not in _GREEK_VOWELS:
            trailing_consonants += 1
        else:
            break  # first non-consonant from the right stops the count

    if trailing_consonants >= 2:
        # ``len(stem) - trailing_consonants`` is the index of the first
        # consonant in the trailing cluster.  The vowel immediately before
        # it is one position earlier.  We strip the vowel and the consonant
        # cluster that follows it, keeping everything to the left.
        cluster_start = len(stem) - trailing_consonants
        vowel_pos = cluster_start - 1  # index of the last vowel before cluster
        if vowel_pos >= 0:             # guard: skip if no vowel precedes cluster
            candidate = stem[:vowel_pos]   # exclude the vowel itself
            if len(candidate) >= MIN_STEM_LEN:
                stem = candidate

    return stem
