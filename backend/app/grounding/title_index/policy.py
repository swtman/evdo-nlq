"""Per-class matching policy for entity-title ranking (ADR-020).

ONE FUNCTION, FOUR DIFFERENT MATCHING POLICIES (ADR-020)
------------------------------------------------------------
Course/book titles and university/department names are matched by different
rules, chosen from measurements against the real data (see ``_POLICY``
below and ADR-020 for the full numbers) — not from a preference for
uniformity:

  - **Scorer.** Titles are matched by ``token_sort_ratio`` (whole-phrase
    similarity); institutions are matched by ``WRatio`` (tolerant of a short
    partial mention inside a long label). Measured: a query naming one word
    of a multi-word university label scores >=90 under ``WRatio`` in 44/45
    cases, and under 90 in ALL 45 cases under ``token_sort_ratio`` (median
    53.8) — the scorer choice is not interchangeable between the two jobs.

  - **Candidate generation.** Course/book use FTS5 prefix search (tens of
    thousands of rows; a full scan would be slow). University/department use
    a full table scan (46 / 379 rows; an FTS5 index would be both unused —
    the 500-candidate budget can never bind — AND lossy, dropping 11% of true
    department matches that a full scan would find).

  - **Acronyms.** University search also consults the curated
    ``gazetteer.ACRONYM_MAP`` (ΑΠΘ, ΕΚΠΑ, ...) directly, because acronyms are
    unrankable by any scorer: stem-prefix retrieval finds only 2/15 of them,
    and ``WRatio`` scores only 2/15 above threshold. Without this,
    university search would fail on exactly the input Greek speakers type
    most often.

  - **Score floor.** Course/book keep any match with nonzero similarity
    (``score > 0``) — a fallback to Topic-stems in ``hints.py`` catches weak
    matches. University/department require ``score >= 90`` — the same
    constant ``linker.FUZZY_THRESHOLD`` uses, so a mention resolvable by
    Stage-1 grounding is resolvable here too, and vice versa.

See ``corpus.py`` for the SQLite access these policies drive and
``search.py`` for the public ranking API that dispatches on them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from app.grounding.schema import FTS_CLASSES, TITLE_CLASSES

# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TitleMatch:
    """A single ranked result from ``rank_titles``.

    Attributes
    ----------
    normalized_title : str
        The accent-free, lowercase key used for ranking (output of
        ``normalize_greek`` applied to the raw title/name).
    score : float
        Similarity score in the range [0, 1] (rapidfuzz's raw 0-100 score,
        divided by 100 — see ``_POLICY`` for which scorer produced it).
        Higher is better.
    surface_forms : list[str]
        All raw KG literal strings that normalize to ``normalized_title``.
        Includes both ALL-CAPS accent-free variants ("ΑΡΧΙΤΕΚΤΟΝΙΚΗ
        ΥΠΟΛΟΓΙΣΤΩΝ") and mixed-case accented variants ("Αρχιτεκτονική
        Υπολογιστών"), whichever are present in the KG. The caller should
        emit all of them in a SPARQL ``VALUES`` binding so the query matches
        regardless of how the title is stored.
    entity_class : str
        Which corpus this match came from — one of ``TITLE_CLASSES``.
        Trailing and defaulted so existing construction sites (before this
        field existed) still compile.
    parents : list[str]
        Parent university name(s), for ``entity_class == "department"``
        only. Sorted, deduplicated, non-empty when the department has any
        recorded parent — a department shared across several universities
        (joint programmes, or simply a common name like "ΠΛΗΡΟΦΟΡΙΚΗΣ") has
        more than one entry. Always ``[]`` for course/book/university.
    """

    normalized_title: str
    score: float
    surface_forms: list[str] = field(default_factory=list)
    entity_class: str = "course"
    parents: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-class matching policy (ADR-020)
# ---------------------------------------------------------------------------

# The shared threshold between this module's institution matching and
# linker.FUZZY_THRESHOLD (linker.py imports this constant rather than
# defining its own, so "resolvable by browsing" and "resolvable by Stage-1
# grounding" are guaranteed to mean the same score cutoff). 90.0 was chosen
# empirically (ADR-020 M4): against the real 46 university labels, a floor of
# 90 keeps 129/132 genuinely-matching queries and rejects all 1267/1267
# mismatched ones tried — moving to 85 keeps the same 129/132 with no
# precision gain, and going lower starts admitting false positives.
INSTITUTION_MATCH_THRESHOLD: float = 90.0


@dataclass(frozen=True)
class _MatchPolicy:
    """How one entity class is candidate-generated, scored, and filtered.

    See the module docstring "ONE FUNCTION, FOUR DIFFERENT MATCHING
    POLICIES" for the measurements behind each field.
    """

    scorer: Callable[..., float]  # a rapidfuzz scorer, e.g. fuzz.WRatio / fuzz.token_sort_ratio
    use_fts: bool  # FTS5 candidate generation, or a full table scan
    acronyms: bool  # also consult gazetteer.ACRONYM_MAP directly
    min_score: float  # raw 0-100 floor (see _clears_floor for the
    # inclusive/exclusive distinction)
    inclusive_floor: bool  # True: score >= min_score. False: score > min_score.


_POLICY: dict[str, _MatchPolicy] = {
    "course": _MatchPolicy(
        scorer=fuzz.token_sort_ratio,
        use_fts=True,
        acronyms=False,
        min_score=0.0,
        inclusive_floor=False,
    ),
    "book": _MatchPolicy(
        scorer=fuzz.token_sort_ratio,
        use_fts=True,
        acronyms=False,
        min_score=0.0,
        inclusive_floor=False,
    ),
    "university": _MatchPolicy(
        scorer=fuzz.WRatio,
        use_fts=False,
        acronyms=True,
        min_score=INSTITUTION_MATCH_THRESHOLD,
        inclusive_floor=True,
    ),
    "department": _MatchPolicy(
        scorer=fuzz.WRatio,
        use_fts=False,
        acronyms=False,
        min_score=INSTITUTION_MATCH_THRESHOLD,
        inclusive_floor=True,
    ),
}

# Sanity check at import time: _POLICY's FTS classes must exactly match
# schema.FTS_CLASSES — the DDL generator and the ranker must agree on which
# classes have an FTS table, or one of them is silently wrong.
assert {name for name, p in _POLICY.items() if p.use_fts} == FTS_CLASSES
assert set(_POLICY) == set(TITLE_CLASSES)


def _clears_floor(score: float, policy: _MatchPolicy) -> bool:
    """Whether ``score`` (raw rapidfuzz 0-100) survives ``policy``'s floor.

    Course/book use an EXCLUSIVE floor at 0.0 — "any nonzero overlap" — the
    historic behaviour ``rank_titles`` has always had; a weak title match
    still falls back to Topic-stems in ``hints.py``. University/department
    use an INCLUSIVE floor at ``INSTITUTION_MATCH_THRESHOLD`` — ADR-020 M4
    measured the "correct" score distribution sitting with its median
    exactly AT 90.0, so an exclusive ``> 90`` would silently reject roughly
    half of genuine matches.
    """
    if policy.inclusive_floor:
        return score >= policy.min_score
    return score > policy.min_score
