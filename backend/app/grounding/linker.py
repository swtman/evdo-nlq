"""Entity mention resolver for the grounding module.

WHAT THIS MODULE DOES
---------------------
``resolve_mention(mention)`` takes a user-typed entity mention — a Greek string
that is likely a university name, department name, or well-known acronym — and
returns a list of ``ResolvedEntity`` objects that map that mention to exact
``evdx:name`` strings from the EvdoGraph KG.

WHY THREE STAGES?
-----------------
1. **Acronym lookup** — fast O(1) lookup for well-known abbreviations like
   ΑΠΘ, ΕΚΠΑ.  Users very commonly type acronyms, and acronym expansion is
   100% precise, so we short-circuit here whenever possible.

2. **Exact normalized match** — after stripping accents and casefolding, many
   user inputs match the KG label exactly (e.g. a user who copies-pastes the
   full university name).  We use the pre-built normalized indices from
   ``gazetteer.py`` so this is also an O(1) dict lookup.

3. **Fuzzy match (rapidfuzz WRatio)** — covers inflected forms, partial names,
   and typos that pass neither stage 1 nor stage 2.  ``WRatio`` is a composite
   scorer that internally picks the best of several algorithms (partial ratio,
   token set ratio, etc.), making it robust to word-order changes and partial
   name mentions (e.g. "αριστοτελειου" fuzzy-matches
   "αριστοτελειο πανεπιστημιο θεσ/νικης").

DEDUPLICATION
-------------
It is possible for the same canonical label to appear in multiple stages (e.g.
an exact university match that also fires a fuzzy university match, or two
department entries with the same canonical label from different indices).  We
keep the entry with the highest score and deduplicate by ``canonical_label``
before returning.

RETURN CONTRACT
---------------
- Returns ``[]`` for empty input or when nothing scores above ``FUZZY_THRESHOLD``.
- All returned ``ResolvedEntity`` objects have distinct ``canonical_label`` values.
- ``parent_university`` is ``None`` for university entities and a non-empty string
  for department entities.
- ``score`` is exactly ``1.0`` for "acronym" and "exact" methods; it is the raw
  ``rapidfuzz.fuzz.WRatio`` score (0–100) for "fuzzy" matches.
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz, process

from app.grounding.gazetteer import (
    ACRONYM_MAP,
    get_department_index,
    get_normalized_departments,
    get_normalized_universities,
    get_university_index,
)
from app.grounding.normalize import normalize_greek
from app.grounding.title_index import INSTITUTION_MATCH_THRESHOLD

# ---------------------------------------------------------------------------
# Public constant
# ---------------------------------------------------------------------------

FUZZY_THRESHOLD: float = INSTITUTION_MATCH_THRESHOLD
"""Minimum rapidfuzz WRatio score (0–100) required to accept a fuzzy match.

An alias for ``title_index.INSTITUTION_MATCH_THRESHOLD`` rather than its own
constant (ADR-020) — ``title_index.rank_titles(entity_class="university")``
(what the ΟΝΤΟΛΟΓΙΑ page's search card calls) and this module's Stage 3 (what
Stage-1 grounding calls) must agree on the same cutoff, or a university a
user can find by browsing could fail to resolve from natural language, and
vice versa.

90.0 is not a round-number guess — it's the measured floor (ADR-020 M4).
Scored against the real 46 university labels:
  - Genuine partial mentions (one real word from the label) score 90.0 at
    the median, with a p25 also at 90.0 — the "correct" distribution sits
    right on this boundary, which is why the floor must be INCLUSIVE
    (``score >= 90``, not ``score > 90``; see ``title_index._clears_floor``).
  - Mismatched words (from an unrelated department name) score 84.7 at the
    highest observed — so 90 leaves a clear margin, not a knife's edge.
  - Sweeping the floor from 85 to 90 keeps the same 129/132 correct matches
    while rejecting the same 100% of mismatches — 90 has no precision cost
    over 85, and is the more conservative choice.
"""


# ---------------------------------------------------------------------------
# Public data type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedEntity:
    """A single candidate resolution for a user-typed entity mention.

    Attributes
    ----------
    canonical_label:
        The exact ``evdx:name`` string as it appears in the EvdoGraph KG.
        Suitable for direct injection into a SPARQL query (e.g. in a FILTER
        or VALUES clause).
    entity_type:
        ``"university"`` or ``"department"``.
    parent_university:
        ``None`` for university entities.  For department entities, the
        canonical label of the owning university (``evdx:name`` of the
        university that houses this department).
    match_method:
        How the match was found: ``"acronym"``, ``"exact"``, or ``"fuzzy"``.
    score:
        Confidence score.  Exactly ``1.0`` for acronym and exact matches;
        a ``rapidfuzz.fuzz.WRatio`` score in the range 0–100 for fuzzy.
    """

    canonical_label: str
    entity_type: str  # "university" | "department"
    parent_university: str | None  # None for universities
    match_method: str  # "acronym" | "exact" | "fuzzy"
    score: float  # 1.0 for acronym/exact; WRatio score (0–100) for fuzzy


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_normalized_acronym_map() -> dict[str, str]:
    """Return a mapping of normalized acronym → canonical label.

    Normalizing both the key (at build time here) and the mention (at lookup
    time) means that any case variant of an acronym ("απθ", "ΑΠΘ", "Απθ")
    resolves identically.

    The map is built lazily on first call and is lightweight (< 20 entries).
    """
    return {normalize_greek(k): v for k, v in ACRONYM_MAP.items()}


# Module-level cache so we don't re-normalize the acronym map on every call.
_NORMALIZED_ACRONYM_MAP: dict[str, str] | None = None


def _get_normalized_acronym_map() -> dict[str, str]:
    """Return the module-level cached normalized acronym map."""
    global _NORMALIZED_ACRONYM_MAP
    if _NORMALIZED_ACRONYM_MAP is None:
        _NORMALIZED_ACRONYM_MAP = _build_normalized_acronym_map()
    return _NORMALIZED_ACRONYM_MAP


# Stage priority for deduplication — lower number = higher confidence.
# Module-level constant so it isn't rebuilt on every deduplicate call.
# WHY priority, not raw score? Acronym/exact use score=1.0 as a sentinel;
# fuzzy uses WRatio 0–100.  These scales are incomparable: a fuzzy score of
# 100.0 would incorrectly displace an exact match at 1.0.  Priority encodes
# the semantic guarantee that acronym/exact is always more reliable than fuzzy.
_STAGE_PRIORITY: dict[str, int] = {"acronym": 0, "exact": 1, "fuzzy": 2}


def _deduplicate(candidates: list[ResolvedEntity]) -> list[ResolvedEntity]:
    """Deduplicate by ``canonical_label``, keeping the highest-priority entry.

    When the same canonical label appears from multiple resolution stages
    (e.g. an exact university hit and then a fuzzy hit for the same label),
    only the entry with the highest stage priority is kept.

    See ``_STAGE_PRIORITY`` for the ordering rationale.

    Args:
        candidates: Possibly-duplicate list of ``ResolvedEntity`` objects.
                    Must be in stage-emission order (acronym first, then exact,
                    then fuzzy) for the priority logic to work correctly.

    Returns:
        Deduplicated list preserving the highest-priority entry per label,
        in insertion order of first occurrence.
    """

    seen: dict[str, ResolvedEntity] = {}
    for entity in candidates:
        if entity.canonical_label not in seen:
            seen[entity.canonical_label] = entity
        else:
            existing = seen[entity.canonical_label]
            # Keep the entry with lower priority number (higher semantic confidence).
            # Within the same priority, keep the first occurrence (already in ``seen``).
            if _STAGE_PRIORITY[entity.match_method] < _STAGE_PRIORITY[existing.match_method]:
                seen[entity.canonical_label] = entity
    return list(seen.values())


# ---------------------------------------------------------------------------
# Resolution stages
# ---------------------------------------------------------------------------


def _stage1_acronym(normalized_mention: str) -> list[ResolvedEntity]:
    """Stage 1 — acronym lookup.

    Args:
        normalized_mention: The user mention after ``normalize_greek``.

    Returns:
        A list containing one ``ResolvedEntity`` if the mention matches a known
        acronym, otherwise an empty list.
    """
    acr_map = _get_normalized_acronym_map()
    canonical = acr_map.get(normalized_mention)
    if canonical is None:
        return []
    # NOTE: ACRONYM_MAP currently contains only university entries.
    # If department acronyms are ever added, entity_type must be parameterized.
    return [
        ResolvedEntity(
            canonical_label=canonical,
            entity_type="university",
            parent_university=None,
            match_method="acronym",
            score=1.0,
        )
    ]


def _stage2_exact(normalized_mention: str) -> list[ResolvedEntity]:
    """Stage 2 — exact normalized lookup against university and department indices.

    Args:
        normalized_mention: The user mention after ``normalize_greek``.

    Returns:
        List of ``ResolvedEntity`` objects for all exact matches found in the
        university index and/or department index.  Typically 0–2 results.
    """
    results: list[ResolvedEntity] = []

    # University exact match
    for canonical in get_university_index().get(normalized_mention, []):
        results.append(
            ResolvedEntity(
                canonical_label=canonical,
                entity_type="university",
                parent_university=None,
                match_method="exact",
                score=1.0,
            )
        )

    # Department exact match
    for dept_entry in get_department_index().get(normalized_mention, []):
        results.append(
            ResolvedEntity(
                canonical_label=dept_entry["department"],
                entity_type="department",
                parent_university=dept_entry["university"],
                match_method="exact",
                score=1.0,
            )
        )

    return results


def _stage3_fuzzy(normalized_mention: str) -> list[ResolvedEntity]:
    """Stage 3 — fuzzy match via rapidfuzz WRatio.

    Searches both the university label set and the department label set.  Only
    accepts candidates that score >= ``FUZZY_THRESHOLD`` on ``fuzz.WRatio``.

    ``WRatio`` is chosen over the simpler ``ratio`` because it internally
    selects the highest score from multiple algorithms (partial ratio, token
    sort ratio, token set ratio), making it robust to:
      - Inflected endings (αριστοτελειου vs αριστοτελειο ...)
      - Word-order differences
      - Partial mentions (a single word from a multi-word label)

    Args:
        normalized_mention: The user mention after ``normalize_greek``.

    Returns:
        List of ``ResolvedEntity`` objects (at most one university and one
        department) that score above ``FUZZY_THRESHOLD``.  May be empty.
        Note: ``extractOne`` returns only the single best match per list, so
        this stage returns at most 2 results (best university + best department).
    """
    results: list[ResolvedEntity] = []

    # --- University fuzzy search -------------------------------------------
    # Normalized (label, canonical) pairs, precomputed once by gazetteer._load()
    # rather than rebuilt here on every call — see gazetteer.py's module
    # docstring "NORMALIZED LABEL LISTS" for the cost this avoids (~17,000
    # redundant normalize_greek calls per question, before this cache existed).
    normalized_unis = get_normalized_universities()
    norm_uni_labels = [pair[0] for pair in normalized_unis]

    best_uni = process.extractOne(
        normalized_mention,
        norm_uni_labels,
        scorer=fuzz.WRatio,
        score_cutoff=FUZZY_THRESHOLD,
    )
    if best_uni is not None:
        _matched_norm, _score, idx = best_uni
        canonical = normalized_unis[idx][1]
        results.append(
            ResolvedEntity(
                canonical_label=canonical,
                entity_type="university",
                parent_university=None,
                match_method="fuzzy",
                score=float(_score),
            )
        )

    # --- Department fuzzy search -------------------------------------------
    # Same precomputed-cache pattern as universities above.
    normalized_depts = get_normalized_departments()
    norm_dept_labels = [triple[0] for triple in normalized_depts]

    best_dept = process.extractOne(
        normalized_mention,
        norm_dept_labels,
        scorer=fuzz.WRatio,
        score_cutoff=FUZZY_THRESHOLD,
    )
    if best_dept is not None:
        _matched_norm, _score, idx = best_dept
        canonical_dept = normalized_depts[idx][1]
        parent_uni = normalized_depts[idx][2]
        results.append(
            ResolvedEntity(
                canonical_label=canonical_dept,
                entity_type="department",
                parent_university=parent_uni,
                match_method="fuzzy",
                score=float(_score),
            )
        )

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_mention(mention: str) -> list[ResolvedEntity]:
    """Resolve a user-typed entity mention to canonical EvdoGraph KG labels.

    Applies three stages in order (acronym → exact → fuzzy).  All three stages
    are always run and their results are combined before deduplication, so that
    a mention that fires an acronym match can also surface an exact match for the
    same entity (e.g. if the user typed the exact canonical label that happens to
    also be in the acronym map — unlikely but handled correctly).

    Args:
        mention: A user-typed string — may be a university name, department name,
                 acronym, inflected form, or partial name.  Any Unicode Greek
                 string (with or without accents, any case) is accepted.  Empty
                 or whitespace-only strings return ``[]`` immediately.

    Returns:
        A list of ``ResolvedEntity`` objects, deduplicated by ``canonical_label``
        (highest score kept when the same label appears in multiple stages).
        Returns ``[]`` if no stage produces a result above ``FUZZY_THRESHOLD``,
        or if the input is empty/whitespace.

    Examples:
        >>> resolve_mention("ΑΠΘ")
        [ResolvedEntity(canonical_label='ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ', ...)]
        >>> resolve_mention("xyzfoobar123")
        []
        >>> resolve_mention("")
        []
    """
    # Normalize once; all stages operate on the normalized form.
    normalized = normalize_greek(mention)

    # Guard: empty or whitespace-only input (normalize_greek returns "" for these).
    if not normalized:
        return []

    # Collect results from all three stages.
    candidates: list[ResolvedEntity] = []
    candidates.extend(_stage1_acronym(normalized))
    candidates.extend(_stage2_exact(normalized))
    candidates.extend(_stage3_fuzzy(normalized))

    # Deduplicate by canonical_label, keeping the highest-score entry per label.
    return _deduplicate(candidates)
