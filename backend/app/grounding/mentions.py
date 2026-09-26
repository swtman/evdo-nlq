"""Token → entity/stem selection policy for the grounding orchestrator.

Tokenization, sliding-window entity resolution, and stem collection — the
logic that decides which tokens of a question become entities, which become
stems, and which are discarded. Split out (ADR-021) from ``hints.py``, which
retains only orchestration (``build_grounding_hints``) so its module object
stays what ``tests/test_grounding_hints.py`` monkeypatches.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.grounding.gazetteer import longest_entity_key
from app.grounding.lexicon import _GREEK_STOPWORDS, _INSTITUTION_GLUE
from app.grounding.linker import ResolvedEntity, entity_key, resolve_exact, resolve_mention
from app.grounding.normalize import (
    is_content_token,
    is_series_marker,
    normalize_greek,
    word_tokens,
)
from app.grounding.stem import MIN_STEM_LEN, topic_stem

# Priority for deduplicating entity matches across window sizes.
# Lower number = higher semantic confidence.
_STAGE_PRIORITY: dict[str, int] = {"acronym": 0, "exact": 1, "fuzzy": 2}


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------


def _tokenize(
    question: str,
    stopwords: frozenset[str] = _GREEK_STOPWORDS,
    *,
    keep_series_markers: bool = False,
) -> list[str]:
    """Extract word tokens from a Greek/English question string.

    Uses a Unicode-aware regex to pull out runs of letters and runs of digits.
    Then filters:
      - Tokens shorter than 3 characters (too short for meaningful matching).
      - Tokens whose normalized form is in ``stopwords``.
    Digit runs never pass these filters on their own.

    With ``keep_series_markers=True`` a SERIES MARKER is kept although it is
    short — a roman numeral (Greek or Latin letters, "Ι", "ΙΙ", "I", "IV"), a
    1-2 digit number, or one of the letters Α Β Γ Δ — but only when it comes
    directly after a kept content word ("ανάλυση κυκλωμάτων Ι", "Μαθηματικά 2").
    Without it, "ΑΝΑΛΥΣΗ ΚΥΚΛΩΜΑΤΩΝ Ι" and "… ΙΙ" were indistinguishable to the
    title ranker (title-linking plan, decision 4). The adjacency rule and the
    1-2 digit limit keep years ("2022") and book codes ("94700120") — frequent
    in questions — out of the title phrase. See ``normalize.is_series_marker``.

    Args:
        question: Raw user question, any Unicode text.
        stopwords: Set of normalized word forms to exclude.  Defaults to
                   ``lexicon._GREEK_STOPWORDS`` (full topic stopword set).
                   Pass ``lexicon._ENTITY_STOPWORDS`` to retain institution
                   words (e.g. "πανεπιστημιο") for entity disambiguation
                   while still filtering generic stopwords.
        keep_series_markers: Keep series markers that follow a content word.
                   Used for TOPIC tokens (title ranking) only; entity
                   tokens leave it off, so entity resolution is unchanged.

    Returns:
        List of raw token strings that survive the filter (original casing
        preserved so that acronym detection like "ΑΠΘ" works at full uppercase).
    """
    # Word split and the content-word rule are shared with the gazetteer's token-key
    # indexes (normalize.word_tokens / is_content_token), so questions and institution
    # labels are cut into words identically — ADR-032.
    result: list[str] = []
    previous_kept_as_content = False
    for tok in word_tokens(question):
        norm = normalize_greek(tok)
        is_content = is_content_token(tok, stopwords)
        if is_content:
            result.append(tok)
        elif keep_series_markers and previous_kept_as_content and is_series_marker(norm):
            result.append(tok)
        previous_kept_as_content = is_content
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


# ---------------------------------------------------------------------------
# Entity-window selection policy
# ---------------------------------------------------------------------------


@dataclass
class _WindowCandidate:
    """A resolved sliding window — internal data holder for greedy selection."""

    start: int  # index of first token (inclusive)
    end: int  # index past last token (exclusive)
    entities: list[ResolvedEntity]
    best_priority: int  # min _STAGE_PRIORITY across entities (0=acronym)
    best_score: float  # max score across entities
    size: int  # window width in tokens


def _resolve_all_windows(
    entity_tokens: list[str],
) -> dict[tuple[str, str | None], ResolvedEntity]:
    """Resolve entity mentions using greedy span-disjoint window selection.

    Accepts ``entity_tokens`` — a token list built with
    ``lexicon._ENTITY_STOPWORDS`` where institution words like
    "πανεπιστημιο" are **not** filtered out. This allows multi-word
    university name fragments ("πανεπιστημιο πειραια") to form as bigrams
    and beat a conflicting bare-city unigram.

    Algorithm
    ---------
    1.  For every window over ``entity_tokens`` — 1 to 3 tokens, and longer ones
        up to ``gazetteer.longest_entity_key()`` words:
        a.  **Glue guard**: skip windows whose tokens are ALL institution/glue
            words (e.g. bare "πανεπιστημιο").  Such windows partial-match every
            "ΠΑΝΕΠΙΣΤΗΜΙΟ X" at ~100 and would inject a random university.
            Multi-word windows with at least one non-glue token are kept.
        b.  Windows of 1–3 tokens: ``resolve_mention`` (acronym, exact, fuzzy).
            Longer windows: ``resolve_exact`` only — they exist so a long name
            («γεωπονιας ιχθυολογιας υδατινου περιβαλλοντος») matches EXACTLY
            (ADR-032; S41: median 27 ms per question, 36 before — no fuzzy cost).
            Discard windows that return no entity.
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

    Result for "… τμημα βιοχημειας και βιοτεχνολογιας …" (ADR-032):
        - «και» is not a token, so the window is "βιοχημειας βιοτεχνολογιας"; it
          matches ΒΙΟΧΗΜΕΙΑΣ ΚΑΙ ΒΙΟΤΕΧΝΟΛΟΓΙΑΣ exactly through the token key and,
          being 2 tokens, sorts before the exact unigram "βιοτεχνολογιας" →
          ΒΙΟΤΕΧΝΟΛΟΓΙΑΣ (another university), which then overlaps and is dropped.
          Before ADR-032 the bigram matched only fuzzily and lost.

    Args:
        entity_tokens: Token list produced by
                        ``_tokenize(q, lexicon._ENTITY_STOPWORDS)``.

    Returns:
        Dict mapping ``linker.entity_key`` — (label, parent university) —
        to ``ResolvedEntity`` for every accepted entity.  Keyed by the pair,
        not the label: a department label shared by several universities
        ("ΝΟΣΗΛΕΥΤΙΚΗΣ") keeps one entry per university, none chosen
        arbitrarily (ADR-028).  Empty dict if nothing resolves.
    """
    # --- 1. Gather window candidates ------------------------------------------
    candidates: list[_WindowCandidate] = []
    for size in range(1, max(3, longest_entity_key()) + 1):
        for i in range(len(entity_tokens) - size + 1):
            window_toks = entity_tokens[i : i + size]

            # Glue guard: skip all-glue windows (no discriminating non-glue token).
            if all(normalize_greek(t) in _INSTITUTION_GLUE for t in window_toks):
                continue

            window_str = " ".join(window_toks)
            # Long windows: exact only (hash lookups) — see step 1b.
            entities = resolve_mention(window_str) if size <= 3 else resolve_exact(window_str)
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
    best: dict[tuple[str, str | None], ResolvedEntity] = {}

    for cand in candidates:
        span = set(range(cand.start, cand.end))
        if span & accepted_indices:
            continue  # overlaps an already-accepted window — drop
        accepted_indices |= span

        # Merge entities from this window, keeping highest-priority per
        # (label, parent) — same identity as linker._deduplicate.
        for entity in cand.entities:
            key = entity_key(entity)
            if key not in best:
                best[key] = entity
            else:
                existing = best[key]
                if _STAGE_PRIORITY[entity.match_method] < _STAGE_PRIORITY[existing.match_method]:
                    best[key] = entity

    return best


def _tokens_used_by_entity(
    tokens: list[str],
    entities: dict[tuple[str, str | None], ResolvedEntity],
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
        entities: Resolved entities dict (``entity_key`` → ResolvedEntity).
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


# ---------------------------------------------------------------------------
# Stem collection policy
# ---------------------------------------------------------------------------


def _collect_stems(tokens: list[str], claimed_indices: frozenset[int]) -> list[str]:
    """Stem tokens not claimed by high-priority entity resolution.

    Applies ``stem.topic_stem`` (Snowball, ADR-031) to each unclaimed token and
    returns unique stems that are at least ``MIN_STEM_LEN`` (4) characters long.

    A stem equal to the whole word is KEPT: the word is still a valid CONTAINS /
    REGEX string. Dropping such "no-op" stems made «αναλυση» vanish from the hint
    (bug F2) and also dropped English words. Series markers («ιι», «VIII») are
    skipped explicitly — before, a 4-letter marker was only stopped by that no-op rule.

    Args:
        tokens: Filtered raw tokens.
        claimed_indices: Token indices claimed by acronym/exact entity matches.

    Returns:
        Ordered list of unique stem strings (insertion order, deduped).
    """
    seen: set[str] = set()
    result: list[str] = []
    for idx, tok in enumerate(tokens):
        if idx in claimed_indices or is_series_marker(normalize_greek(tok)):
            continue
        stem = topic_stem(tok)
        if len(stem) < MIN_STEM_LEN:
            continue
        if stem not in seen:
            seen.add(stem)
            result.append(stem)
    return result
