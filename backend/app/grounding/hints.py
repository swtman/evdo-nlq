"""Grounding orchestrator — builds hint blocks for LLM system prompts.

WHAT THIS MODULE DOES
---------------------
``build_grounding_hints(question)`` is the single public entry point for the
grounding module.  Given a raw user question (Greek or English), it:

  1. Tokenizes the question into individual word tokens.
  2. Resolves entity mentions (single tokens AND 2/3-token windows) via
     ``linker.resolve_mention``.
  3. Finds course/book title CANDIDATES from the residual content words,
     via ``title_index.search.rank_titles`` — searching BOTH the course and
     book corpora (see "COURSE AND BOOK TITLE RESOLUTION" below).
  4. Stems every topic word not claimed by an acronym/exact entity, via
     ``stem.greek_stem`` — ALWAYS, even when a title candidate was found
     (see "TITLE CANDIDATES, NOT RESOLUTIONS" below).
  5. Formats the results into a markdown block ready for injection into the
     system prompt that precedes the LLM SPARQL-generation call.

This module owns only orchestration. The token→entity/stem selection policy
(tokenization, sliding-window resolution, stem collection) lives in
``mentions.py``; the Greek lexicon data it's built from lives in
``lexicon.py``; the markdown line formatters live in ``hint_lines.py`` (all
split out here, ADR-021). ``build_grounding_hints`` stays in THIS module
deliberately — ``tests/test_grounding_hints.py`` monkeypatches
``hints.rank_titles`` and ``hints.settings`` on this module's own object, so
the function that resolves those names at call time has to keep living here.

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
``hint_lines._format_title_line``) so the LLM can tell them apart, and a
collision note fires only when the SAME title matched both classes — not
merely "a course and a book both matched something" (two different titles
matching is not an ambiguity). See ADR-019.

TITLE CANDIDATES, NOT RESOLUTIONS
----------------------------------
A title that scores above the threshold is emitted as a *candidate*, not a
confirmed binding, and its words still produce topic stems. The ranker only
measures string similarity; it cannot tell whether the question NAMES a
title ("μάθημα Ανάλυση Κυκλωμάτων") or DESCRIBES a topic ("βιβλία
αλγορίθμων", which matches the course ΘΕΩΡΙΑ ΑΛΓΟΡΙΘΜΩΝ). Previously a match
claimed every residual token, so the stems disappeared and the prompt said
"do NOT use CONTAINS" — for the topic reading that silently narrowed the
answer to one course (gold example ex-024). Now both are offered and prompt
v6's Rule 16 tells the model how to choose. Title-linking plan, decision 1;
evidence F10 in notes/investigations/title-linking/.

The section headers in the block are plain labels ("**Entities**:",
"**Title candidates**:", "**Topic stems**:"); the instructions for using
them live in the versioned prompt, not in this module (finding C1).

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

import logging

from app.config import settings
from app.grounding.hint_lines import _accent_last_vowel, _format_entity_line, _format_title_line
from app.grounding.lexicon import _ENTITY_STOPWORDS
from app.grounding.mentions import (
    _collect_stems,
    _resolve_all_windows,
    _tokenize,
    _tokens_used_by_entity,
)
from app.grounding.title_index import TitleMatch, rank_titles

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_grounding_hints(question: str) -> str:
    """Build a grounding hint block to inject into the LLM system prompt.

    Takes a raw user question (Greek or English) and returns a formatted
    markdown string with up to three optional sections:

      - **Entities** — canonical KG labels resolved from the question (exact
        strings to use in SPARQL FILTER/VALUES clauses).
      - **Title candidates** — course/book titles that closely match words in
        the question, class-tagged ``[Course]``/``[Book]`` (see
        "COURSE AND BOOK TITLE RESOLUTION" and "TITLE CANDIDATES, NOT
        RESOLUTIONS" in the module docstring).
      - **Topic stems** — Greek word stems for CONTAINS filters; emitted even
        when title candidates exist.

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
    logger.info("Grounding input: %r", question)

    if not question.strip():
        logger.info("Grounding output: (empty question — no hints)")
        return ""

    # Step 1a — entity tokens: keep institution words so multi-word university
    #            name fragments form as bigrams (e.g. "πανεπιστημιο πειραια"
    #            scores 92.7 for ΠΑΝΕΠΙΣΤΗΜΙΟ ΠΕΙΡΑΙΩΣ vs bare "πειραια" → ΤΕΙ).
    entity_tokens = _tokenize(question, _ENTITY_STOPWORDS)
    # Step 1b — topic tokens: full stopword set (including attribute nouns like
    #            "καθηγητεσ") so only genuine content words survive for title
    #            ranking and stemming.
    #            Series markers ("Ι", "ΙΙ", "2", "Α") after a content word are
    #            kept so numbered titles can be told apart (decision 4); they
    #            never produce stems (too short / no-op, see _collect_stems).
    topic_tokens = _tokenize(question, keep_series_markers=True)

    if not entity_tokens and not topic_tokens:
        logger.info("Grounding output: (no entity/topic tokens — no hints)")
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
                m
                for m in rank_titles(phrase, k=3, entity_class="course")
                if m.score >= settings.course_match_threshold
            ]
        if settings.book_linking_enabled:
            book_matches = [
                m
                for m in rank_titles(phrase, k=3, entity_class="book")
                if m.score >= settings.book_match_threshold
            ]
    title_matches: list[TitleMatch] = course_matches + book_matches

    # Step 5 — stem every topic word not claimed by an acronym/exact ENTITY.
    # A matched title does NOT consume its words: it is only a *candidate*
    # (see "TITLE CANDIDATES, NOT RESOLUTIONS" in the module docstring), so the
    # stems stay available for the case where the question describes a topic
    # rather than naming a title (ex-024: "βιβλία αλγορίθμων" matched
    # ΘΕΩΡΙΑ ΑΛΓΟΡΙΘΜΩΝ and, before this change, lost its `αλγορ` stem).
    stems = _collect_stems(topic_tokens, claimed)

    # Step 6 — nothing found → bail out early.
    if not entities and not title_matches and not stems:
        logger.info("Grounding output: (nothing resolved — no hints)")
        return ""

    # Step 7 — format the output block.
    lines: list[str] = ["## Resolved entities & terms", ""]

    # Section headers are plain LABELS. How to use each section is explained
    # in the versioned prompt (Rule 16 of prompts/nl-to-sparql-v6.md), not
    # here — project rule: prompt text lives in prompts/, never inlined in
    # code (title-linking plan, finding C1).
    if entities:
        lines.append("**Entities**:")
        for entity in entities.values():
            lines.append(_format_entity_line(entity))

    if title_matches:
        if entities:
            lines.append("")  # blank line between entities and titles
        lines.append("**Title candidates**:")
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
            # A fact only; what to do about it is Rule 16 of prompt v6.
            lines.append(f'(Note: "{representative}" matched BOTH a Course and a Book.)')

    if stems:
        if entities or title_matches:
            lines.append("")  # blank line before stems section
        lines.append("**Topic stems**:")
        for stem in stems:
            accented = _accent_last_vowel(stem)
            if accented and accented != stem:
                lines.append(f"- {stem} | {accented}")
            else:
                lines.append(f"- {stem}")

    result = "\n".join(lines)
    logger.info("Grounding output:\n%s", result)
    return result
