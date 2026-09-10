"""Token → entity/stem selection policy for the grounding orchestrator.

Tokenization, sliding-window entity resolution, and stem collection — the
logic that decides which tokens of a question become entities, which become
stems, and which are discarded. Split out (ADR-021) from ``hints.py``, which
retains only orchestration (``build_grounding_hints``) so its module object
stays what ``tests/test_grounding_hints.py`` monkeypatches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.grounding.lexicon import _GREEK_STOPWORDS, _INSTITUTION_GLUE
from app.grounding.linker import ResolvedEntity, resolve_mention
from app.grounding.normalize import normalize_greek
from app.grounding.stem import greek_stem

# Priority for deduplicating entity matches across window sizes.
# Lower number = higher semantic confidence.
_STAGE_PRIORITY: dict[str, int] = {"acronym": 0, "exact": 1, "fuzzy": 2}


# ---------------------------------------------------------------------------
# Tokenization
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
                   ``lexicon._GREEK_STOPWORDS`` (full topic stopword set).
                   Pass ``lexicon._ENTITY_STOPWORDS`` to retain institution
                   words (e.g. "πανεπιστημιο") for entity disambiguation
                   while still filtering generic stopwords.

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


def _resolve_all_windows(entity_tokens: list[str]) -> dict[str, ResolvedEntity]:
    """Resolve entity mentions using greedy span-disjoint window selection.

    Accepts ``entity_tokens`` — a token list built with
    ``lexicon._ENTITY_STOPWORDS`` where institution words like
    "πανεπιστημιο" are **not** filtered out. This allows multi-word
    university name fragments ("πανεπιστημιο πειραια") to form as bigrams
    and beat a conflicting bare-city unigram.

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
        entity_tokens: Token list produced by
                        ``_tokenize(q, lexicon._ENTITY_STOPWORDS)``.

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


# ---------------------------------------------------------------------------
# Stem collection policy
# ---------------------------------------------------------------------------


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
