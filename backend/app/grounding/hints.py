"""Grounding orchestrator — builds hint blocks for LLM system prompts.

WHAT THIS MODULE DOES
---------------------
``build_grounding_hints(question)`` is the single public entry point for the
grounding module.  Given a raw user question (Greek or English), it:

  1. Tokenizes the question: entity tokens (``mentions._tokenize``) and the
     analysed question for titles and stems (``mentions.analyse_question`` —
     ``title_key`` tokens, naming cues, quotes, entity claims; ADR-035).
  2. Resolves entity mentions (sliding windows) via ``linker.resolve_mention``.
  3. Finds the SPANS of the question that name a course/book title, via
     ``title_index.spans.link_title_spans`` — searching BOTH the course and
     book corpora (see "COURSE AND BOOK TITLE RESOLUTION" and "SPANS, CUES,
     NAMED TITLES" below).
  4. Stems every content word that no entity claimed and no NAMED title
     covers, via ``stem.topic_stem`` (Snowball, ADR-031) — also the words of
     a title CANDIDATE (see "TITLE CANDIDATES, NOT RESOLUTIONS" below) — and
     lists each stem with its accent-proof regex (``stem.stem_pattern``).
  5. Formats the results into a markdown block ready for injection into the
     user message that follows the question (ADR-026).

This module owns only orchestration. The token→entity/stem selection policy
(tokenization, sliding-window resolution, the claim rule, stem collection)
lives in ``mentions.py``; the Greek lexicon data it's built from lives in
``lexicon.py``; the markdown line formatters live in ``hint_lines.py`` (all
split out here, ADR-021). ``build_grounding_hints`` stays in THIS module
deliberately — ``tests/test_grounding_hints.py`` monkeypatches
``hints.link_title_spans`` and ``hints.settings`` on this module's own object, so
the function that resolves those names at call time has to keep living here.

SPANS, CUES, NAMED TITLES (branch 6, ADR-035)
---------------------------------------------
Until branch 6 every leftover content word was joined into ONE phrase and
ranked whole against the titles, so framing words («υπάρχει», «ονομάζεται»,
other entities) pulled the score under the cut-off (finding F1; dev set
78/115 named titles found). Now ``link_title_spans`` scores every window of
the question (stopwords allowed inside, never at the edges; ≥ 2 content
words unless named with a cue) and keeps the best non-overlapping ones
(S45: 113/115). A span right after a naming cue («ονομάζεται», «με τίτλο»)
or inside quotation marks is NAMED: it goes under ``**Named titles**`` and
its words get no stems (decision 1: a cue makes the binding firm; prompt v9
Rule 16). Every other span is a ``**Title candidates**`` line, with stems.

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
A title that scores above the threshold WITHOUT a naming cue is emitted as a
*candidate*, not a confirmed binding, and its words still produce topic stems. The ranker only
measures string similarity; it cannot tell whether the question NAMES a
title ("μάθημα Ανάλυση Κυκλωμάτων") or DESCRIBES a topic ("βιβλία
αλγορίθμων", which matches the course ΘΕΩΡΙΑ ΑΛΓΟΡΙΘΜΩΝ). Previously a match
claimed every residual token, so the stems disappeared and the prompt said
"do NOT use CONTAINS" — for the topic reading that silently narrowed the
answer to one course (gold example ex-024). Now both are offered and prompt
v6's Rule 16 tells the model how to choose. Title-linking plan, decision 1;
evidence F10 in notes/investigations/title-linking/.

The section headers in the block are plain labels ("**Entities**:",
"**Named titles**:", "**Title candidates**:", "**Topic stems**:"); the instructions for using
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
not appear verbatim in any book title, but the stem "αλγοριθμ" does appear in
"ΑΛΓΟΡΙΘΜΟΙ ΚΑΙ ΔΟΜΕΣ ΔΕΔΟΜΕΝΩΝ". Each stem line also gives the regex the model
should use — ``- αλγοριθμ → [αά]λγ[οό]ρ[ιίϊΐ]θμ`` — so the accented mixed-case
titles ("Αλγόριθμοι…") match too; how to use it is Rule 16 of prompt v8.

DEDUPLICATION ACROSS WINDOWS
------------------------------
The same entity may fire for multiple overlapping windows (e.g. a bigram and
a trigram that both resolve to the same entity).  We keep the highest-priority
match (acronym > exact > fuzzy) per ``linker.entity_key`` — the (label, parent
university) pair — matching the contract of ``linker._deduplicate``.

A department label shared by several universities ("ΝΟΣΗΛΕΥΤΙΚΗΣ" exists at
7; the name, with its "(…)" variants, at 19) is therefore kept once PER
UNIVERSITY, and the hint prints one line per label listing every university
("[Department @ A | B | …] LABEL"). The block never narrows to the university
the question names: listing all of them cannot contradict the question, and
"other than X" questions still see every label (ADR-028; before, the label
alone was the key and one arbitrary university survived — 135/548 in S11).
"""

from __future__ import annotations

import logging

from app.config import settings
from app.grounding.hint_lines import _format_entity_lines, _format_title_line
from app.grounding.lexicon import _ENTITY_STOPWORDS
from app.grounding.mentions import (
    _collect_stems,
    _resolve_all_windows,
    _tokenize,
    analyse_question,
)
from app.grounding.stem import stem_pattern
from app.grounding.title_index.spans import link_title_spans

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_grounding_hints(question: str) -> str:
    """Build a grounding hint block to inject into the LLM system prompt.

    Takes a raw user question (Greek or English) and returns a formatted
    markdown string with up to four optional sections:

      - **Entities** — canonical KG labels resolved from the question (exact
        strings to use in SPARQL FILTER/VALUES clauses).
      - **Named titles** — course/book titles the question names with a cue
        («ονομάζεται», «με τίτλο», quotes): firm bindings (ADR-035).
      - **Title candidates** — course/book titles that closely match other
        words of the question, class-tagged ``[Course]``/``[Book]`` (see
        "COURSE AND BOOK TITLE RESOLUTION" and "TITLE CANDIDATES, NOT
        RESOLUTIONS" in the module docstring).
      - **Topic stems** — Greek word stems with their REGEX pattern; emitted
        even when title candidates exist (not for the words of a named title).

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
    # Step 1b — the question as title spans and stems see it: title_key tokens,
    #            content words, naming cues, quotes, and the tokens entities claim
    #            (acronyms, exact universities, a department after «τμήμα») — ADR-035.
    analysed = analyse_question(question)

    if not entity_tokens and not any(analysed.content):
        logger.info("Grounding output: (no entity/topic tokens — no hints)")
        return ""

    # Step 2 — resolve entity mentions using greedy span-disjoint windows.
    entities = _resolve_all_windows(entity_tokens)

    # Step 3 — title spans, BOTH classes (see "COURSE AND BOOK TITLE RESOLUTION"
    # and "SPANS, CUES, NAMED TITLES" in the module docstring).
    classes = tuple(
        cls
        for cls, enabled in (
            ("course", settings.course_linking_enabled),
            ("book", settings.book_linking_enabled),
        )
        if enabled
    )
    spans = (
        link_title_spans(analysed, threshold=settings.title_span_threshold, classes=classes)
        if classes
        else []
    )
    named = [s for s in spans if s.cued]
    candidates = [s for s in spans if not s.cued]

    # Step 4 — stem every content word that no entity claimed and no NAMED title
    # covers. An un-cued title is only a *candidate* (decision 1), so its words keep
    # their stems for the topic reading (ex-024: "βιβλία αλγορίθμων" matched
    # ΘΕΩΡΙΑ ΑΛΓΟΡΙΘΜΩΝ and once lost its `αλγορ` stem). Naming cues are not
    # content words, so «ονομαζ»/«τιτλ» never become stems.
    in_named = {i for s in named for i in range(s.start, s.end)}
    stem_tokens = [
        tok
        for i, tok in enumerate(analysed.tokens)
        if analysed.content[i]
        and i not in analysed.claimed
        and i not in in_named
        and tok.isalpha()  # stem_pattern takes letters only («covid19» has no stem)
    ]
    stems = _collect_stems(stem_tokens, frozenset())

    # Step 5 — nothing found → bail out early.
    if not entities and not spans and not stems:
        logger.info("Grounding output: (nothing resolved — no hints)")
        return ""

    # Step 6 — format the output block.
    lines: list[str] = ["## Resolved entities & terms", ""]

    # Section headers are plain LABELS. How to use each section is explained
    # in the versioned prompt (Rule 16 of prompts/nl-to-sparql-v9.md), not
    # here — project rule: prompt text lives in prompts/, never inlined in
    # code (title-linking plan, finding C1).
    if entities:
        lines.append("**Entities**:")
        # One line per label; a department shared by several universities
        # lists all of them (ADR-028).
        lines.extend(_format_entity_lines(entities.values()))

    # Named titles first (the question names them — firm), then candidates.
    # Within a section: courses, then books; each in question order, best first
    # per span. Deterministic order matters: the LLM DiskCache key is a hash of
    # the full prompt, so nondeterministic ordering would halve the cache hit
    # rate for no benefit.
    for header, group in (("**Named titles**:", named), ("**Title candidates**:", candidates)):
        if not group:
            continue
        if len(lines) > 2:
            lines.append("")  # blank line after the previous section
        lines.append(header)
        for cls in ("course", "book"):
            for span in group:
                if span.entity_class == cls:
                    lines.extend(_format_title_line(m) for m in span.matches)

    # Collision note — fires ONLY when the SAME normalized title matched both
    # classes, not merely "a course and a book both matched something" (two
    # different titles matching is not an ambiguity, and a note there would be
    # factually false). See module docstring "COURSE AND BOOK TITLE RESOLUTION".
    course_matches = [m for s in spans if s.entity_class == "course" for m in s.matches]
    book_norms = {m.normalized_title for s in spans if s.entity_class == "book" for m in s.matches}
    for norm in sorted({m.normalized_title for m in course_matches} & book_norms):
        representative = next(
            m.surface_forms[0] for m in course_matches if m.normalized_title == norm
        )
        # A fact only; what to do about it is Rule 16 of the prompt.
        lines.append(f'(Note: "{representative}" matched BOTH a Course and a Book.)')

    if stems:
        if len(lines) > 2:
            lines.append("")  # blank line before stems section
        lines.append("**Topic stems**:")
        # "stem → pattern": the stem for the reader, the pattern for the SPARQL
        # REGEX (prompt v8, Rule 16). One pattern covers accent-free and accented
        # titles, replacing v7's "stem | stém" pair (ADR-031).
        for stem in stems:
            lines.append(f"- {stem} → {stem_pattern(stem)}")

    result = "\n".join(lines)
    logger.info("Grounding output:\n%s", result)
    return result
