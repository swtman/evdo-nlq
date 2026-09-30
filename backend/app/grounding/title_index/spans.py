"""Span-based title linking — which words of a QUESTION name a course/book title (ADR-035).

WHY THIS EXISTS
---------------
Until branch 6, grounding joined every leftover content word of the question into ONE phrase
and ranked that whole phrase against the titles (``rank_titles``, ``token_sort_ratio``, cut-off
0.70). A title among other words could not win: «σε ποιες σχολές υπάρχει μάθημα που ονομάζεται
ανάλυση κυκλωμάτων» compared «υπαρχει οποιο ονομαζεται αναλυση κυκλωματων» with the title and
scored 0.625 (finding F1). On the frozen dev set 78/115 named titles were found, «ονομάζεται»
questions 1/17, two titles in one question 0/8 (ADR-034). There was no mention detection — the
stopword list stood in for one (entity linking = spotting → candidates → disambiguation; we had
only the last two, F4).

This module is the spotting step: approach B of the title-linking plan (F7, fuzzy windows)
with the issue-9 rules, measured in S45 on the dev split (113/115 found, ~35 ms per question).

HOW IT WORKS
------------
1. ``parse_question`` cuts the question with ``title_key`` — the SAME function that built the
   stored ``norm`` column (ADR-024), so «Γ1» stays one token as in the title — and marks every
   token: content word (≥ 3 characters, not digits, not a series marker, not a stopword, not a
   cue), naming cue (``lexicon._TITLE_CUES``: «ονομάζεται», «τίτλο», …), and quoted runs
   («…», "…", “…”). The caller (``mentions.analyse_question``) adds the tokens entities claim.
2. Windows: every token run that starts on a content word and ends on a content word — or,
   after its first token, on a series marker / a token with a digit («… ΙΙ», «… Γ1») — up to
   ``MAX_SPAN_TOKENS``. Stopwords, short words and class words sit INSIDE a window freely
   («εισαγωγή στον προγραμματισμό»); a cue or a claimed token ends it. A quoted run is always a
   window, whatever its edges — the user drew them. A window may also START on the token
   directly after a cue («με τίτλο το …»), and it is CUED when only non-content words stand
   between it and the cue (dev tg-114/119: «λέγεται Οι ασφαλείς πόλεις»). Every window holds
   at least one content word.
3. Retrieve once, align many: ONE FTS5 query per class with the stems of all content words
   (the existing ``_fts_query_terms`` / ``_fts_candidates``, 500 candidates by bm25 — S45: a
   2,000 budget changed nothing), then every window is scored against those candidates in memory
   with the class's scorer (``process.extract``; ``cdist`` would need numpy). F10 measured the
   one-SQLite-query-per-window version at a 484 ms median; this one ~35 ms.
4. Accept a window when its best score ≥ the threshold (``settings.title_span_threshold``,
   0.85 — S45: 0.80 lets every nonexistent dev title through, 0.90 loses recall) AND it has
   ≥ 2 content words or is CUED (right after a cue, or quoted). The ≥ 2 rule is the single-word
   guard (decision 2: a bare word is a topic — its stem returns a superset of the exact title's
   rows, while a wrong exact binding silently drops rows); series markers count 0 (decision 4).
5. Select score-first: (score ↓, content words ↓, span length ↓), greedy, non-overlapping;
   the same span may also add the other class (a title that is both a course and a book). S45:
   size-first (F7's P1) let a framing verb glued to a near title («διδάσκεται εισαγωγή στον
   προγραμματισμό», 0.86) beat the exact title (1.00) — F7 needed size-first only for a typo'd
   two-word span against an exact one-word title, which the guard now removes anyway.
6. Each accepted span lists up to ``LINES_PER_SPAN`` titles above the threshold (numbered
   siblings «… Ι», «… ΙΙ»), hydrated by ``search._hydrate`` exactly as ``rank_titles`` does.

ONE SEARCH PATH, TWO ENTRY POINTS
---------------------------------
``rank_titles`` (a typed phrase → ranked titles) still serves the ΟΝΤΟΛΟΓΙΑ page / API;
``link_title_spans`` (a question → the spans that name titles) serves grounding. Both use the
same key (``policy.key``), candidate generator, scorer and hydration — ADR-035 amends the
backend/CLAUDE.md rule accordingly. What a question can reach and a phrase cannot: nothing
beyond the span rules above (a one-word title needs a cue).

Known limits (S45, dev): a title that starts with an article («Τα οικονομικά της υγείας») is
found without it unless quoted; ``token_sort_ratio`` ignores word order, so a span crossing two
titles can match a third one (tg-217); a typo in a title's first word can lose to a shorter
exact title (tg-094); shortened titles («της Γραμμικής») stay topics by design.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import process

from app.grounding import db
from app.grounding.lexicon import _GREEK_STOPWORDS, _TITLE_CUES
from app.grounding.normalize import is_series_marker, title_key
from app.grounding.schema import FTS_CLASSES
from app.grounding.title_index.corpus import _build_index, _fts_candidates, _IndexState
from app.grounding.title_index.policy import _POLICY, TitleMatch
from app.grounding.title_index.search import _fts_query_terms, _hydrate

# Longest window in tokens: KG title length p99 = 14 tokens (F6).
MAX_SPAN_TOKENS = 14
# Title lines per accepted span — the numbered siblings (S45: top-3 found 113/115, top-1 111).
LINES_PER_SPAN = 3
# Text between quotation marks: «…», "…" or “…”.
_QUOTED_RE = re.compile(r"«([^«»]+)»|\"([^\"]+)\"|“([^“”]+)”")
# Deterministic class order in the output (and the hint block): courses, then books.
_CLASS_ORDER = {"course": 0, "book": 1}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpanQuestion:
    """A question cut into ``title_key`` tokens, with what each token is.

    Attributes:
        tokens: ``title_key(question).split()``.
        content: Per token — a content word (can start/end a span, counts for the ≥ 2 rule).
        cue: Per token — a naming cue (``lexicon._TITLE_CUES``); never inside a span.
        quoted: ``(start, end)`` token runs that were inside quotation marks.
        claimed: Token indices an entity took (``mentions.analyse_question``): acronyms,
            exact university names, a department name after «τμήμα». No span crosses them.
    """

    tokens: tuple[str, ...]
    content: tuple[bool, ...]
    cue: tuple[bool, ...]
    quoted: frozenset[tuple[int, int]] = frozenset()
    claimed: frozenset[int] = frozenset()


@dataclass(frozen=True)
class SpanMatch:
    """Titles of ONE class that a span of the question names.

    Attributes:
        start / end: Token range ``[start, end)`` in ``SpanQuestion.tokens``.
        cued: Right after a naming cue, or quoted — the question NAMES the title (decision 1:
            a firm binding, prompt v9's "Named titles"); otherwise a candidate.
        entity_class: ``"course"`` or ``"book"``.
        matches: Up to ``LINES_PER_SPAN`` titles, best first (scores in 0..1).
    """

    start: int
    end: int
    cued: bool
    entity_class: str
    matches: list[TitleMatch] = field(default_factory=list)


@dataclass(frozen=True)
class _Window:
    start: int
    end: int
    text: str
    content_words: int
    cued: bool


# ---------------------------------------------------------------------------
# Question analysis (pure — no database, no entity linker)
# ---------------------------------------------------------------------------


def _find_run(tokens: tuple[str, ...], run: list[str]) -> tuple[int, int] | None:
    """First position of ``run`` inside ``tokens`` as ``(start, end)``, or None."""
    for i in range(len(tokens) - len(run) + 1):
        if run and list(tokens[i : i + len(run)]) == run:
            return (i, i + len(run))
    return None


def parse_question(question: str) -> SpanQuestion:
    """Cut a question into ``title_key`` tokens and mark content words, cues and quotes.

    Claims are left empty; ``mentions.analyse_question`` adds them (it needs the entity
    linker, which this package must not import — the dependency direction is
    gazetteer → title_index → linker).

    Examples:
        >>> parse_question("μάθημα που ονομάζεται «Ανάλυση Κυκλωμάτων»").tokens
        ('μαθημα', 'που', 'ονομαζεται', 'αναλυση', 'κυκλωματων')
    """
    tokens = tuple(title_key(question).split())
    cue = tuple(t in _TITLE_CUES for t in tokens)
    content = tuple(
        len(t) >= 3
        and not t.isdigit()
        and t not in _GREEK_STOPWORDS
        and not cue[i]
        and not is_series_marker(t)
        for i, t in enumerate(tokens)
    )
    quoted = set()
    for m in _QUOTED_RE.finditer(question):
        inner = next(g for g in m.groups() if g is not None)
        run = _find_run(tokens, title_key(inner).split())
        if run:
            quoted.add(run)
    return SpanQuestion(tokens=tokens, content=content, cue=cue, quoted=frozenset(quoted))


def _after_cue(q: SpanQuestion) -> list[bool]:
    """Per token: a naming cue precedes it with only non-content words in between.

    «με τίτλο το χρονικον …», «λέγεται η ανάλυση …»: an article may stand between the cue and
    the title (dev tg-114/119); a content word ends the cue's reach.
    """
    out = [False] * len(q.tokens)
    active = False
    for i in range(len(q.tokens)):
        out[i] = active
        if q.cue[i]:
            active = True
        elif q.content[i]:
            active = False
    return out


def _windows(q: SpanQuestion) -> list[_Window]:
    """Every candidate span of the question (see the module docstring, step 2)."""
    out: dict[tuple[int, int], _Window] = {}
    n = len(q.tokens)
    after_cue = _after_cue(q)
    for i in range(n):
        # A span starts on a content word — or on anything right after a cue, so a title
        # that begins with an article («Η Εποχή των Αλγορίθμων») can be matched whole.
        directly_after_cue = i > 0 and q.cue[i - 1] and not q.cue[i]
        if not (q.content[i] or directly_after_cue) or i in q.claimed:
            continue
        for j in range(i + 1, min(n, i + MAX_SPAN_TOKENS) + 1):
            last = j - 1
            if q.cue[last] or last in q.claimed:
                break
            tail = q.tokens[last]
            numbered_end = last > i and (is_series_marker(tail) or any(ch.isdigit() for ch in tail))
            if not (q.content[last] or numbered_end):
                continue
            words = sum(q.content[i:j])
            if not words:  # «το 2022» after a cue: no content word, no title
                continue
            cued = after_cue[i] or (i, j) in q.quoted
            out[(i, j)] = _Window(i, j, " ".join(q.tokens[i:j]), words, cued)
    for i, j in q.quoted:  # a quoted run is a window whatever its edges
        span = range(i, j)
        if (
            (i, j) not in out
            and any(q.content[p] for p in span)
            and not any(p in q.claimed or q.cue[p] for p in span)
        ):
            out[(i, j)] = _Window(i, j, " ".join(q.tokens[i:j]), sum(q.content[i:j]), True)
    return sorted(out.values(), key=lambda w: (w.start, w.end))


# ---------------------------------------------------------------------------
# Linking
# ---------------------------------------------------------------------------


def _link(q: SpanQuestion, states: dict[str, _IndexState], threshold: float) -> list[SpanMatch]:
    """Score every window against each class's candidates; select; hydrate (steps 3–6)."""
    windows = _windows(q)
    if not windows:
        return []
    content_words = [t for i, t in enumerate(q.tokens) if q.content[i] and i not in q.claimed]
    terms = _fts_query_terms(" ".join(content_words))
    if not terms:
        return []
    floor = threshold * 100.0

    # (window, class, ranked [(key, raw score)]) for every window that clears the rules
    scored: list[tuple[_Window, str, list[tuple[str, float]]]] = []
    for cls, state in states.items():
        candidates = _fts_candidates(state, terms)
        if not candidates:
            continue
        scorer = _POLICY[cls].scorer
        for w in windows:
            ranked = process.extract(w.text, candidates, scorer=scorer, limit=LINES_PER_SPAN * 4)
            ranked_ok = [(key, score) for key, score, _idx in ranked if score >= floor]
            if ranked_ok and (w.content_words >= 2 or w.cued):
                scored.append((w, cls, ranked_ok))

    # Score-first greedy selection; the same span may add the other class.
    scored.sort(
        key=lambda s: (
            -s[2][0][1],
            -s[0].content_words,
            -(s[0].end - s[0].start),
            s[0].start,
            _CLASS_ORDER.get(s[1], 9),
        )
    )
    used: set[int] = set()
    classes_at: dict[tuple[int, int], set[str]] = {}
    accepted: list[tuple[_Window, str, list[tuple[str, float]]]] = []
    for w, cls, ranked in scored:
        key = (w.start, w.end)
        if key in classes_at:
            if cls not in classes_at[key]:
                classes_at[key].add(cls)
                accepted.append((w, cls, ranked))
            continue
        if used & set(range(w.start, w.end)):
            continue
        used.update(range(w.start, w.end))
        classes_at[key] = {cls}
        accepted.append((w, cls, ranked))

    accepted.sort(key=lambda a: (a[0].start, _CLASS_ORDER.get(a[1], 9)))
    return [
        SpanMatch(
            start=w.start,
            end=w.end,
            cued=w.cued,
            entity_class=cls,
            matches=_hydrate(states[cls], ranked, LINES_PER_SPAN),
        )
        for w, cls, ranked in accepted
    ]


def link_title_spans(
    question: SpanQuestion,
    *,
    threshold: float,
    classes: tuple[str, ...] = ("course", "book"),
) -> list[SpanMatch]:
    """The spans of ``question`` that name a course/book title, in question order.

    Opens one read-only connection to ``entities.db`` for the call (like ``rank_titles``).

    Args:
        question: From ``mentions.analyse_question`` (tokens, cues, quotes, claims).
        threshold: Minimum similarity in 0..1 (``settings.title_span_threshold``).
        classes: Which title classes to search (``settings.*_linking_enabled``).

    Returns:
        One ``SpanMatch`` per (span, class); ``[]`` when nothing clears the rules.
    """
    classes = tuple(c for c in classes if c in FTS_CLASSES)
    if not classes:
        return []
    conn = db.get_connection()
    try:
        return _link(question, {c: _IndexState(conn=conn, table=c) for c in classes}, threshold)
    finally:
        conn.close()


def link_title_spans_from_corpus(
    corpora: dict[str, dict[str, list[str]]],
    question: SpanQuestion,
    *,
    threshold: float,
    classes: tuple[str, ...] = ("course", "book"),
) -> list[SpanMatch]:
    """``link_title_spans`` over in-memory fixture corpora (tests only).

    Args:
        corpora: ``{class: {grouping key: [surface, ...]}}`` — keys are re-derived from the
            surfaces exactly as the real builder does (see ``corpus._build_index``).
        question, threshold, classes: As for ``link_title_spans``.
    """
    states = {c: _build_index(corpora.get(c, {}), c) for c in classes if c in FTS_CLASSES}
    try:
        return _link(question, states, threshold)
    finally:
        for state in states.values():
            state.conn.close()
