"""Grounding orchestrator — builds hint blocks for LLM system prompts.

WHAT THIS MODULE DOES
---------------------
``build_grounding_hints(question)`` is the single public entry point for the
grounding module.  Given a raw user question (Greek or English), it:

  1. Tokenizes the question into individual word tokens.
  2. Resolves entity mentions (single tokens AND 2/3-token windows) via
     ``linker.resolve_mention``.
  3. Resolves a specific course/book title from the residual content words,
     via ``title_index.rank_titles`` — searching BOTH the course and book
     corpora (see "COURSE AND BOOK TITLE RESOLUTION" below).
  4. Stems remaining topic words via ``stem.greek_stem``.
  5. Formats the results into a markdown block ready for injection into the
     system prompt that precedes the LLM SPARQL-generation call.

COURSE AND BOOK TITLE RESOLUTION
-----------------------------------
Both corpora are searched on every question (when their respective
``settings.course_linking_enabled`` / ``settings.book_linking_enabled`` flags
are on), not just one guessed from question wording. The obvious alternative
— detect "βιβλία" vs. "μάθημα" and search only that corpus — was rejected:
those exact words are stopwords, already stripped from ``topic_tokens``
before title ranking runs, and the signal is unreliable in the direction
that matters most ("ποια βιβλία χρησιμοποιεί το μάθημα Χ" says "βιβλία" but
names a Course). A wrong guess would silently search the wrong corpus and
find nothing — the same invisible-failure shape as the whitespace bug this
module's title matching was extended to fix (see ``clean.py``).

Because both corpora are searched, the same normalized title can legitimately
match both a Course and a Book (measured: ~3,498 titles exist in both). The
output is tagged ``[Course]``/``[Book]`` per resolved title (see
``_format_title_line``) so the LLM can tell them apart, and a collision note
fires only when the SAME title matched both classes — not merely "a course
and a book both matched something" (two different titles matching is not an
ambiguity). See ADR-019.

WHY INJECT HINTS INTO THE SYSTEM PROMPT?
-----------------------------------------
The LLM must produce SPARQL that uses exact ``evdx:name`` strings (e.g.
"ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ") because EvdoGraph does not support
free-text full-text search — all filters are FILTER(CONTAINS(...)) or exact
VALUES.  If the model guesses a name it tends to hallucinate partial or
accented variants that return zero results.  Grounding resolves the user's
intent (e.g. "ΑΠΘ") to the canonical KG label before the model runs, so the
hint block can say "use this exact string".

Topic stems solve the inflection problem: "αλγοριθμων" (genitive plural) does
not appear verbatim in any book title, but the stem "αλγορ" does appear as a
CONTAINS substring of the normalized title "ΑΛΓΟΡΙΘΜΟΙ ΚΑΙ ΔΟΜΕΣ ΔΕΔΟΜΕΝΩΝ".

DEDUPLICATION ACROSS WINDOWS
------------------------------
The same canonical label may fire for multiple overlapping windows (e.g. a
bigram and a trigram that both resolve to the same entity).  We keep the
highest-priority match (acronym > exact > fuzzy) per canonical label, matching
the contract of ``linker._deduplicate``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import settings
from app.grounding.linker import ResolvedEntity, resolve_mention
from app.grounding.normalize import normalize_greek
from app.grounding.stem import greek_stem
from app.grounding.title_index import TitleMatch, rank_titles

# ---------------------------------------------------------------------------
# Greek stopwords (normalized form — accent-free, lowercase, ς→σ)
# ---------------------------------------------------------------------------

_GREEK_STOPWORDS: frozenset[str] = frozenset({
    # Articles
    "ο", "η", "το", "οι", "τα", "τον", "την", "τησ", "του", "των", "τοισ", "ταισ",
    # Prepositions
    "σε", "στο", "στη", "στον", "στην", "στα", "απο", "για", "στισ", "απ",
    "μεσ", "με", "κατα", "προσ", "ωσ", "περι",
    # Conjunctions
    "και", "η", "αλλα", "ομωσ", "ενω", "οτι", "που", "πωσ",
    # Pronouns
    "εγω", "εσυ", "αυτοσ", "αυτη", "αυτο", "αυτοι", "αυτεσ", "αυτα",
    "ποιοσ", "ποια", "ποιο",
    # Common verbs
    "ειναι", "εχει", "εχουν", "ειχε", "εχω", "θελω",
    # Question words (all case forms so residual phrase stays clean for title ranking)
    "ποια", "ποιοσ", "ποιεσ", "ποιων", "ποσα", "ποτε", "που", "πωσ", "γιατι",
    "ποιουσ",   # acc pl. masc. "ποιους" — e.g. "ποιους καθηγητές ..."
    # Attribute/role nouns (what the user is ASKING for, not part of the title)
    # Filtering these keeps the title-ranking phrase clean.
    "καθηγητεσ", "καθηγητη", "καθηγητησ", "καθηγητεσ",  # professor (various cases)
    "συγγραφεασ", "συγγραφεισ", "συγγραφεα",              # author
    "εκδοτησ", "εκδοτεσ",                                  # publisher
    # Common domain nouns (too generic to be useful stems)
    "βιβλια", "βιβλιο", "μαθημα", "μαθηματα", "κουρσα", "κορσα",
    "τμημα", "πανεπιστημιο", "τεχνολογικο", "ιδρυμα",
    "σχολη", "σχολεσ", "σχολων", "ετοσ", "χρονια",
    # Numbers as words
    "ενα", "δυο", "τρια", "τεσσερα",
})

# Institution-type words that are stopwords for topic stemming but must be
# KEPT for entity disambiguation.  E.g. "πανεπιστημιο" in the phrase
# "πανεπιστημιο πειραια" distinguishes ΠΑΝΕΠΙΣΤΗΜΙΟ ΠΕΙΡΑΙΩΣ from ΤΕΙ ΠΕΙΡΑΙΑ;
# stripping it first causes the bare "πειραια" unigram to match ΤΕΙ (score 90)
# instead of the University (score 92.7 for the full bigram).
_INSTITUTION_WORDS: frozenset[str] = frozenset({
    "πανεπιστημιο", "τμημα", "σχολη", "σχολεσ", "σχολων",
    "τεχνολογικο", "ιδρυμα",
})

# Stopword set for entity tokenization — identical to _GREEK_STOPWORDS but
# retaining institution words so multi-word university fragments survive as
# sliding windows for the entity linker.
_ENTITY_STOPWORDS: frozenset[str] = _GREEK_STOPWORDS - _INSTITUTION_WORDS

# Glue-only words: tokens that carry NO discriminating entity information on
# their own.  A bare "πανεπιστημιο" unigram partial-matches every
# "ΠΑΝΕΠΙΣΤΗΜΙΟ X" at ~100 via rapidfuzz partial_ratio, injecting a random
# university.  Windows whose tokens are ALL glue words are skipped.
# Multi-word windows that merely *contain* a glue word ("πανεπιστημιο πειραια")
# are kept — they have a discriminating non-glue token ("πειραια").
_INSTITUTION_GLUE: frozenset[str] = _INSTITUTION_WORDS | frozenset({
    "πολυτεχνειο", "τει", "ανωτατο", "ανωτατη",
})

# Priority for deduplicating entity matches across window sizes.
# Lower number = higher semantic confidence.
_STAGE_PRIORITY: dict[str, int] = {"acronym": 0, "exact": 1, "fuzzy": 2}

# The KG stores titles in both ALL-CAPS accent-free ("ΑΛΓΟΡΙΘΜΟΙ") and
# mixed-case accented ("Αλγόριθμοι"). SPARQL's LCASE() strips case but NOT
# Unicode accents, so CONTAINS(LCASE("Αλγόριθμοι"), "αλγορ") is false because
# ό (U+03CC) ≠ ο (U+03BF). We emit both the plain stem and the version with
# the last vowel accented to cover both storage styles in one FILTER.
_GREEK_VOWELS_STR: str = "αεηιουω"
_VOWEL_TO_ACCENTED: dict[int, str] = str.maketrans("αεηιουω", "άέήίόύώ")


def _accent_last_vowel(stem: str) -> str | None:
    """Return stem with its last vowel accented, or None if no vowel found."""
    for i in reversed(range(len(stem))):
        if stem[i] in _GREEK_VOWELS_STR:
            return stem[:i] + stem[i].translate(_VOWEL_TO_ACCENTED) + stem[i + 1:]
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _tokenize(
    question: str,
    stopwords: frozenset[str] = _GREEK_STOPWORDS,
) -> list[str]:
    """Extract word-only tokens from a Greek/English question string.

    Uses a Unicode-aware regex to pull out sequences of non-whitespace,
    non-punctuation, non-digit characters.  Then filters:
      - Tokens shorter than 3 characters (too short for meaningful matching).
      - Tokens whose normalized form is in ``stopwords``.

    Args:
        question: Raw user question, any Unicode text.
        stopwords: Set of normalized word forms to exclude.  Defaults to
                   ``_GREEK_STOPWORDS`` (full topic stopword set).  Pass
                   ``_ENTITY_STOPWORDS`` to retain institution words (e.g.
                   "πανεπιστημιο") for entity disambiguation while still
                   filtering generic stopwords.

    Returns:
        List of raw token strings that survive the filter (original casing
        preserved so that acronym detection like "ΑΠΘ" works at full uppercase).
    """
    # re.findall with a Unicode word-char pattern: letters only (no digits, no punct).
    raw_tokens: list[str] = re.findall(r"[^\s\W\d]+", question, flags=re.UNICODE)

    result: list[str] = []
    for tok in raw_tokens:
        if len(tok) < 3:  # too short to be meaningful
            continue
        if normalize_greek(tok) in stopwords:
            continue
        result.append(tok)
    return result


def _sliding_windows(tokens: list[str], size: int) -> list[str]:
    """Generate joined sliding windows of ``size`` tokens from ``tokens``.

    Args:
        tokens: List of raw token strings.
        size: Window size (2 for bigrams, 3 for trigrams).

    Returns:
        List of space-joined window strings.  Empty if len(tokens) < size.
    """
    return [" ".join(tokens[i : i + size]) for i in range(len(tokens) - size + 1)]


@dataclass
class _WindowCandidate:
    """A resolved sliding window — internal data holder for greedy selection."""

    start: int                      # index of first token (inclusive)
    end: int                        # index past last token (exclusive)
    entities: list[ResolvedEntity]
    best_priority: int              # min _STAGE_PRIORITY across entities (0=acronym)
    best_score: float               # max score across entities
    size: int                       # window width in tokens


def _resolve_all_windows(entity_tokens: list[str]) -> dict[str, ResolvedEntity]:
    """Resolve entity mentions using greedy span-disjoint window selection.

    Accepts ``entity_tokens`` — a token list built with ``_ENTITY_STOPWORDS``
    where institution words like "πανεπιστημιο" are **not** filtered out.
    This allows multi-word university name fragments ("πανεπιστημιο πειραια")
    to form as bigrams and beat a conflicting bare-city unigram.

    Algorithm
    ---------
    1.  For every unigram/bigram/trigram window over ``entity_tokens``:
        a.  **Glue guard**: skip windows whose tokens are ALL institution/glue
            words (e.g. bare "πανεπιστημιο").  Such windows partial-match every
            "ΠΑΝΕΠΙΣΤΗΜΙΟ X" at ~100 and would inject a random university.
            Multi-word windows with at least one non-glue token are kept.
        b.  Call ``resolve_mention``; discard windows that return no entity.
    2.  Sort surviving candidates by ``(best_priority asc, size desc,
        best_score desc)``:
        - Priority first — acronym unigrams (priority 0, e.g. ΑΠΘ, ΕΚΠΑ) are
          always accepted before lower-confidence fuzzy bigrams.
        - Larger window before smaller, within the same priority — so
          "πανεπιστημιο πειραια" (size 2, score 92.7) sorts before the
          bare "πειραια" unigram (size 1, score 90.0).
    3.  Greedy acceptance: maintain a set of consumed token indices.  Accept a
        candidate only if its span does not overlap consumed indices; mark its
        span consumed.

    Result for "… πανεπιστημιο πειραια":
        - bigram accepted first (span {0,1}), emits ΠΑΝΕΠΙΣΤΗΜΙΟ ΠΕΙΡΑΙΩΣ.
        - unigram "πειραια" at index 1 overlaps → dropped.  ΤΕΙ ΠΕΙΡΑΙΑ never
          surfaces.

    Result for "ΑΠΘ … ΕΚΠΑ" (regression guard):
        - Both acronym unigrams (priority 0) sort first and are accepted with
          non-overlapping spans; no fuzzy bigram displaces them.

    Args:
        entity_tokens: Token list produced by ``_tokenize(q, _ENTITY_STOPWORDS)``.

    Returns:
        Dict mapping ``canonical_label → ResolvedEntity`` for every accepted
        entity.  Empty dict if nothing resolves.
    """
    # --- 1. Gather window candidates ------------------------------------------
    candidates: list[_WindowCandidate] = []
    for size in (1, 2, 3):
        for i in range(len(entity_tokens) - size + 1):
            window_toks = entity_tokens[i : i + size]

            # Glue guard: skip all-glue windows (no discriminating non-glue token).
            if all(normalize_greek(t) in _INSTITUTION_GLUE for t in window_toks):
                continue

            window_str = " ".join(window_toks)
            entities = resolve_mention(window_str)
            if not entities:
                continue

            best_priority = min(_STAGE_PRIORITY[e.match_method] for e in entities)
            best_score = max(e.score for e in entities)
            candidates.append(
                _WindowCandidate(
                    start=i,
                    end=i + size,
                    entities=entities,
                    best_priority=best_priority,
                    best_score=best_score,
                    size=size,
                )
            )

    # --- 2. Sort: highest confidence first, then largest context window --------
    candidates.sort(key=lambda c: (c.best_priority, -c.size, -c.best_score))

    # --- 3. Greedy span-disjoint acceptance ------------------------------------
    accepted_indices: set[int] = set()
    best: dict[str, ResolvedEntity] = {}

    for cand in candidates:
        span = set(range(cand.start, cand.end))
        if span & accepted_indices:
            continue  # overlaps an already-accepted window — drop
        accepted_indices |= span

        # Merge entities from this window, keeping highest-priority per label.
        for entity in cand.entities:
            if entity.canonical_label not in best:
                best[entity.canonical_label] = entity
            else:
                existing = best[entity.canonical_label]
                if _STAGE_PRIORITY[entity.match_method] < _STAGE_PRIORITY[existing.match_method]:
                    best[entity.canonical_label] = entity

    return best


def _tokens_used_by_entity(
    tokens: list[str],
    entities: dict[str, ResolvedEntity],
    high_priority_methods: frozenset[str],
) -> frozenset[int]:
    """Identify which token indices were claimed by high-priority entity matches.

    We only skip stemming for tokens that contributed to an acronym or exact
    match.  Fuzzy-matched tokens remain candidates for stemming because the
    fuzzy match may be spurious.

    WHY? A fuzzy match of e.g. "αριστοτελειου" (partial inflection of a long
    university name) with score 85 is useful as an entity hint but the same
    word is also useful as a stem.  Blocking it from stemming would lose
    information; the LLM can use both.

    Args:
        tokens: Filtered raw tokens.
        entities: Resolved entities dict (canonical_label → ResolvedEntity).
        high_priority_methods: Match methods that count as "entity claimed"
            (typically {"acronym", "exact"}).

    Returns:
        Frozenset of token indices whose text, as a window, was resolved by a
        high-priority method.  Single-token windows only (multi-token windows
        are handled by checking membership below).
    """
    # Build set of normalized single-token strings that were claimed.
    # Re-resolve each token individually to find those that fire at high priority.
    claimed_indices: set[int] = set()
    for idx, tok in enumerate(tokens):
        matches = resolve_mention(tok)
        for m in matches:
            if m.match_method in high_priority_methods:
                claimed_indices.add(idx)
                break
    return frozenset(claimed_indices)


def _collect_stems(tokens: list[str], claimed_indices: frozenset[int]) -> list[str]:
    """Stem tokens not claimed by high-priority entity resolution.

    Applies ``greek_stem`` to each unclaimed token and returns unique stems that:
      - Are at least 4 characters long (``MIN_STEM_LEN``).
      - Differ from the full normalized token (a no-op stem adds no value).

    Args:
        tokens: Filtered raw tokens.
        claimed_indices: Token indices claimed by acronym/exact entity matches.

    Returns:
        Ordered list of unique stem strings (insertion order, deduped).
    """
    from app.grounding.normalize import normalize_greek as _norm
    from app.grounding.stem import MIN_STEM_LEN

    seen: set[str] = set()
    result: list[str] = []
    for idx, tok in enumerate(tokens):
        if idx in claimed_indices:
            continue
        stem = greek_stem(tok)
        if len(stem) < MIN_STEM_LEN:
            continue
        # Skip no-op stems (stem == fully normalized token — stripping nothing).
        normalized_tok = _norm(tok)
        if stem == normalized_tok:
            continue
        if stem not in seen:
            seen.add(stem)
            result.append(stem)
    return result


def _format_entity_line(entity: ResolvedEntity) -> str:
    """Format a single entity as a markdown bullet line.

    University: ``- [University] CANONICAL_LABEL``
    Department: ``- [Department @ PARENT_UNIVERSITY] CANONICAL_LABEL``

    Args:
        entity: A resolved entity from the linker.

    Returns:
        A markdown bullet string (no trailing newline).
    """
    if entity.entity_type == "university":
        return f"- [University] {entity.canonical_label}"
    # Department — include parent university for SPARQL context.
    parent = entity.parent_university or "unknown"
    return f"- [Department @ {parent}] {entity.canonical_label}"


# Display label per TitleMatch.entity_class — keys must match schema.TITLE_CLASSES.
_TITLE_CLASS_LABELS: dict[str, str] = {"course": "Course", "book": "Book"}


def _format_title_line(match: TitleMatch) -> str:
    """Format a single resolved title as a class-tagged markdown bullet.

    One line per TITLE, not per surface form — multiple surface forms (e.g.
    the ALL-CAPS accent-free and mixed-case accented KG storage variants of
    the same title) are joined with " | ", reusing the convention the
    Topic-stems section already uses for "variants of the same thing", so
    the model isn't taught a second syntax for the same idea.

    Example: ``- [Course] "ΑΡΧΙΤΕΚΤΟΝΙΚΗ ΥΠΟΛΟΓΙΣΤΩΝ" | "Αρχιτεκτονική Υπολογιστών"``

    Args:
        match: A ``TitleMatch`` with its ``entity_class`` set.

    Returns:
        A markdown bullet string (no trailing newline).
    """
    label = _TITLE_CLASS_LABELS[match.entity_class]
    surfaces = " | ".join(f'"{s}"' for s in match.surface_forms)
    return f"- [{label}] {surfaces}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_grounding_hints(question: str) -> str:
    """Build a grounding hint block to inject into the LLM system prompt.

    Takes a raw user question (Greek or English) and returns a formatted
    markdown string with up to three optional sections:

      - **Entities** — canonical KG labels resolved from the question (exact
        strings to use in SPARQL FILTER/VALUES clauses).
      - **Resolved title(s)** — specific course/book titles resolved from the
        question, class-tagged ``[Course]``/``[Book]`` (see
        "COURSE AND BOOK TITLE RESOLUTION" in the module docstring).
      - **Topic stems** — Greek word stems for CONTAINS filters.

    Returns ``""`` (empty string) when the question yields neither entities nor
    useful stems — the caller should skip injection in that case.

    Args:
        question: Raw user question, any Unicode text.  May be Greek, English,
                  or mixed.  Empty string is handled gracefully (returns "").

    Returns:
        A non-empty markdown string ready for injection, OR ``""`` if the
        grounding pipeline found nothing useful.

    Examples:
        >>> build_grounding_hints("ποια βιβλία αλγορίθμων προτείνει το ΑΠΘ;")
        '## Resolved entities & terms\\n\\n**Entities** ...'
        >>> build_grounding_hints("τι και η")
        ''
    """
    if not question.strip():
        return ""

    # Step 1a — entity tokens: keep institution words so multi-word university
    #            name fragments form as bigrams (e.g. "πανεπιστημιο πειραια"
    #            scores 92.7 for ΠΑΝΕΠΙΣΤΗΜΙΟ ΠΕΙΡΑΙΩΣ vs bare "πειραια" → ΤΕΙ).
    entity_tokens = _tokenize(question, _ENTITY_STOPWORDS)
    # Step 1b — topic tokens: full stopword set (including attribute nouns like
    #            "καθηγητεσ") so only genuine content words survive for title
    #            ranking and stemming.
    topic_tokens = _tokenize(question)

    if not entity_tokens and not topic_tokens:
        return ""

    # Step 2 — resolve entity mentions using greedy span-disjoint windows.
    entities = _resolve_all_windows(entity_tokens)

    # Step 3 — determine which topic tokens are "claimed" by high-priority hits.
    high_priority = frozenset({"acronym", "exact"})
    claimed = _tokens_used_by_entity(topic_tokens, entities, high_priority)

    # Step 4a — title ranking, BOTH classes.
    # Take the residual content words (unclaimed, non-stopword tokens) as the
    # candidate phrase for a specific course/book title the user named, e.g.
    # "αρχιτεκτονικη υπολογιστων" after "ΑΠΘ" is claimed and stopwords removed.
    # Search course and book independently — see "COURSE AND BOOK TITLE
    # RESOLUTION" in the module docstring for why this is unconditional
    # rather than gated on a guessed class.
    residual_tokens = [t for i, t in enumerate(topic_tokens) if i not in claimed]
    course_matches: list[TitleMatch] = []
    book_matches: list[TitleMatch] = []
    if residual_tokens:
        phrase = " ".join(residual_tokens)
        if settings.course_linking_enabled:
            # Apply acceptance threshold — below it the match is too
            # uncertain; fall back to stem-CONTAINS for this query.
            course_matches = [
                m for m in rank_titles(phrase, k=3, entity_class="course")
                if m.score >= settings.course_match_threshold
            ]
        if settings.book_linking_enabled:
            book_matches = [
                m for m in rank_titles(phrase, k=3, entity_class="book")
                if m.score >= settings.book_match_threshold
            ]
    title_matches: list[TitleMatch] = course_matches + book_matches

    # Step 4b — if any title matched (either class), consume the residual
    # tokens so they don't also produce stems.  The exact VALUES binding
    # makes CONTAINS redundant for whichever title(s) were resolved.
    if title_matches:
        # All residual topic tokens are now covered by the title resolution.
        claimed = frozenset(range(len(topic_tokens)))

    # Step 5 — stem remaining unclaimed topic words (fallback when no title fired).
    stems = _collect_stems(topic_tokens, claimed)

    # Step 6 — nothing found → bail out early.
    if not entities and not title_matches and not stems:
        return ""

    # Step 7 — format the output block.
    lines: list[str] = ["## Resolved entities & terms", ""]

    if entities:
        lines.append("**Entities** (use the exact label in FILTER/VALUES):")
        for entity in entities.values():
            lines.append(_format_entity_line(entity))

    if title_matches:
        if entities:
            lines.append("")  # blank line between entities and titles
        lines.append(
            "**Resolved title(s)** (the question names one or more specific KG"
            " titles — bind the tagged class's evdx:title to these exact"
            " literals with VALUES; do NOT use CONTAINS for them):"
        )
        # Courses first, then books; each group already sorted score-descending
        # by rank_titles. Deterministic order matters: the LLM DiskCache key is
        # a hash of the full prompt, so nondeterministic ordering would halve
        # the cache hit rate for no benefit.
        for match in course_matches:
            lines.append(_format_title_line(match))
        for match in book_matches:
            lines.append(_format_title_line(match))

        # Collision note — fires ONLY when the SAME normalized title matched
        # both classes, not merely "a course and a book both matched
        # something" (two different titles matching is not an ambiguity, and
        # a note there would be factually false). See module docstring
        # "COURSE AND BOOK TITLE RESOLUTION".
        course_norms = {m.normalized_title for m in course_matches}
        book_norms = {m.normalized_title for m in book_matches}
        for norm in sorted(course_norms & book_norms):
            representative = next(
                m.surface_forms[0] for m in course_matches if m.normalized_title == norm
            )
            lines.append(
                f'(Note: "{representative}" matched BOTH a Course and a Book.'
                " Bind only the class the question is about; if it asks for"
                " the books of a named course, bind the [Course] title and"
                " reach the books via evdx:hasBook.)"
            )

    if stems:
        if entities or title_matches:
            lines.append("")  # blank line before stems section
        lines.append(
            '**Topic stems** (use in CONTAINS(LCASE(?label), "stem");'
            " if two variants are shown separated by |, use both with ||):"
        )
        for stem in stems:
            accented = _accent_last_vowel(stem)
            if accented and accented != stem:
                lines.append(f"- {stem} | {accented}")
            else:
                lines.append(f"- {stem}")

    return "\n".join(lines)
