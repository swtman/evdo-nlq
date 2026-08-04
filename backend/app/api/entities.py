"""GET /entities/search, GET /entities/list — search & browse KG entities.

WHY THESE ENDPOINTS EXIST
--------------------------
Two different parts of the app need to look up KG entity names by a partial
or inflected phrase:
  1. The ΟΝΤΟΛΟΓΙΑ page's search cards (course/book/university/department),
     where a user browses what exists in the KG.
  2. Stage 1 grounding (``app/grounding/hints.py``), which resolves an entity
     named inside a natural-language question *before* the LLM runs, so it
     can bind an exact SPARQL VALUES clause instead of an under-constrained
     CONTAINS filter (see ADR-015, ADR-018, ADR-020).

Both call the SAME ranking function — ``app.grounding.title_index.rank_titles``
— so an entity a user can find by browsing here is exactly one the SPARQL
pipeline is capable of matching from a natural-language mention (course/book
via ``hints.py``'s title resolution; university/department via
``linker.py``'s Stage 3, which shares the same score threshold — see
``title_index.INSTITUTION_MATCH_THRESHOLD``). This endpoint is that
function's HTTP-facing twin: grounding calls ``rank_titles`` in-process (no
network hop); this endpoint calls it for the frontend, which cannot reach
Python functions directly and needs an HTTP interface.

SCOPE
-----
All four classes in ``schema.TITLE_CLASSES`` — ``course``, ``book``,
``university``, ``department`` — return real, live-ranked results from
``GET /entities/search``. Each is matched by a different policy tuned to how
that class is actually typed (see ``title_index._POLICY`` and ADR-020): a
course/book search is whole-phrase similarity, an institution search
tolerates a short partial mention and also checks known acronyms directly.

``GET /entities/list`` is a SEPARATE, simpler endpoint: it returns every
entry of a class alphabetically, with no query phrase and no ranking. Only
``schema.LISTABLE_CLASSES`` (``university``, ``department``) support it —
course (~73k titles) and book (~37k titles) are far too large to ever
meaningfully "list"; browsing those is what ``/entities/search`` with an
empty-ish query used to attempt, and still isn't the right tool. This keeps
"rank a phrase" and "show me everything" as two distinct operations instead
of overloading one endpoint's empty-query behaviour to mean both.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.grounding.schema import LISTABLE_CLASSES, TITLE_CLASSES
from app.grounding.title_index import list_titles, rank_titles

router = APIRouter()


class EntitySearchResult(BaseModel):
    """One ranked (or, from ``/entities/list``, alphabetically listed) result.

    Fields
    ------
    title : str
        A display-ready surface form of the matched entity (the mixed-case
        accented KG variant when one exists, otherwise whatever form is
        stored). See ``_pick_display_surface``.
    score : float
        Similarity score in [0, 1], from ``TitleMatch.score``. Higher means
        a closer match to the query phrase. Always ``1.0`` for
        ``/entities/list`` results (listing implies no similarity judgement).
    parents : list[str]
        Parent university name(s) — populated only for
        ``class=department`` results; ``[]`` for every other class. A
        department name shared by several universities (a common name, or a
        joint programme) has more than one parent.
    """

    title: str
    score: float
    parents: list[str] = []


class EntitySearchResponse(BaseModel):
    """Response body for GET /entities/search and GET /entities/list."""

    query: str
    results: list[EntitySearchResult]
    total: int


def _pick_display_surface(surface_forms: list[str]) -> str:
    """Pick the most readable surface form to show in a search result list.

    The KG stores some titles/names ALL-CAPS accent-free ("ΑΡΧΙΤΕΚΤΟΝΙΚΗ
    ΥΠΟΛΟΓΙΣΤΩΝ") and others mixed-case accented ("Αρχιτεκτονική
    Υπολογιστών"). For a search UI, showing the mixed-case accented form
    (when available) reads far better than shouting in all-caps. Falls back
    to the first surface form if every variant happens to be all-uppercase
    (the common case for universities/departments — see ``gazetteer.py``'s
    "The EvdoGraph KG stores names in ALL-CAPS" note).

    The returned string has its whitespace collapsed for display ONLY — the
    database (and everything the grounding pipeline binds into SPARQL)
    deliberately keeps the raw KG literal untouched, including any invisible
    characters (see ``app/grounding/clean.py``). A visible leading tab or
    embedded non-breaking space is a presentation nuisance here, not a
    correctness concern, so it's fine to tidy up only at this final step.

    Args:
        surface_forms: Non-empty list of raw KG literal strings for one
                        normalized title/name (``TitleMatch.surface_forms``).

    Returns:
        The chosen display string, whitespace-collapsed.
    """
    for surface in surface_forms:
        if surface != surface.upper():  # has at least one lowercase letter
            return " ".join(surface.split())
    return " ".join(surface_forms[0].split())


@router.get("/entities/search", response_model=EntitySearchResponse)
def search_entities(
    q: str = Query(..., min_length=1, description="Search phrase, Greek or English"),
    entity_class: str = Query(
        "course",
        alias="class",
        description="Entity type to search: 'course', 'book', 'university', or 'department'",
    ),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
) -> EntitySearchResponse:
    """Search KG entity names by phrase, ranked by similarity to ``q``.

    Calls the exact same ``rank_titles`` function the SPARQL grounding
    pipeline uses (see module docstring) — no separate search logic to keep
    in sync. Each class is matched by its own policy (see
    ``title_index._POLICY``); the response shape is identical regardless.

    Returns 400 if ``class`` is not one of the supported values.
    """
    if entity_class not in TITLE_CLASSES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported class {entity_class!r}. Supported: {sorted(TITLE_CLASSES)}",
        )

    matches = rank_titles(q, k=limit, entity_class=entity_class)
    results = [
        EntitySearchResult(
            title=_pick_display_surface(m.surface_forms), score=m.score, parents=m.parents
        )
        for m in matches
    ]
    return EntitySearchResponse(query=q, results=results, total=len(results))


@router.get("/entities/list", response_model=EntitySearchResponse)
def list_entities(
    entity_class: str = Query(
        ...,
        alias="class",
        description="Entity type to list: 'university' or 'department'",
    ),
    limit: int = Query(1000, ge=1, le=1000, description="Maximum number of results"),
) -> EntitySearchResponse:
    """List every entity of a small class, alphabetically — no ranking.

    Backs the "δείτε τα όλα" browse tier on the ΟΝΤΟΛΟΓΙΑ page's University
    and Department cards. NOT a search endpoint — there is no ``q`` phrase
    and every result has ``score=1.0``. See module docstring "SCOPE" for why
    this is a separate endpoint from ``/entities/search`` rather than that
    endpoint's empty-query behaviour.

    Returns 400 if ``class`` is not in ``LISTABLE_CLASSES`` (course/book are
    far too large to list; use ``/entities/search`` for those).
    """
    if entity_class not in LISTABLE_CLASSES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported class {entity_class!r} for listing. "
                f"Supported: {sorted(LISTABLE_CLASSES)}. "
                "Use /entities/search for course or book."
            ),
        )

    matches = list_titles(entity_class=entity_class, limit=limit)
    results = [
        EntitySearchResult(
            title=_pick_display_surface(m.surface_forms), score=m.score, parents=m.parents
        )
        for m in matches
    ]
    return EntitySearchResponse(query="", results=results, total=len(results))
