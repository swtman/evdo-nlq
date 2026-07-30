"""
GET /entities/search — search KG entities (courses, books) by name.

WHY THIS ENDPOINT EXISTS
--------------------------
Two different parts of the app need to look up course/book titles by a
partial or inflected phrase:
  1. The ΟΝΤΟΛΟΓΙΑ page's course search box, where a user browses what
     exists in the KG.
  2. Stage 1 grounding (``app/grounding/hints.py``), which resolves a course
     named inside a natural-language question *before* the LLM runs, so it
     can bind an exact SPARQL VALUES clause instead of an under-constrained
     CONTAINS filter (see ADR-015, ADR-018).

Both call the SAME ranking function — ``app.grounding.title_index.rank_titles``
— so a course a user can find by browsing here is exactly a course the SPARQL
pipeline is capable of matching from a natural-language mention. This
endpoint is that function's HTTP-facing twin: grounding calls ``rank_titles``
in-process (no network hop, it runs inside the same request that generates
SPARQL); this endpoint calls it for the frontend, which cannot reach Python
functions directly and needs an HTTP interface.

SCOPE
-----
Only ``class=course`` returns real results right now. ``class=book`` is
accepted but always returns an empty list — no book title corpus has been
built yet (see ADR-018's "Deferred" section). This lets the frontend book
search box call the same endpoint shape today and light up automatically
once a book corpus lands, with no endpoint changes needed.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.grounding.title_index import rank_titles

router = APIRouter()

# class= values this endpoint currently understands. "book" is accepted (so
# the frontend doesn't need a feature flag) but always yields empty results
# until a book corpus exists.
_SUPPORTED_CLASSES = {"course", "book"}


class EntitySearchResult(BaseModel):
    """One ranked search result.

    Fields
    ------
    title : str
        A display-ready surface form of the matched title (the mixed-case
        accented KG variant when one exists, otherwise whatever form is
        stored). See ``_pick_display_surface``.
    score : float
        Similarity score in [0, 1], from ``TitleMatch.score``. Higher means
        a closer match to the query phrase.
    """

    title: str
    score: float


class EntitySearchResponse(BaseModel):
    """Response body for GET /entities/search."""

    query: str
    results: list[EntitySearchResult]
    total: int


def _pick_display_surface(surface_forms: list[str]) -> str:
    """Pick the most readable surface form to show in a search result list.

    The KG stores some titles ALL-CAPS accent-free ("ΑΡΧΙΤΕΚΤΟΝΙΚΗ
    ΥΠΟΛΟΓΙΣΤΩΝ") and others mixed-case accented ("Αρχιτεκτονική
    Υπολογιστών"). For a search UI, showing the mixed-case accented form
    (when available) reads far better than shouting in all-caps. Falls back
    to the first surface form if every variant happens to be all-uppercase.

    Args:
        surface_forms: Non-empty list of raw KG title strings for one
                        normalized title (``TitleMatch.surface_forms``).

    Returns:
        The chosen display string.
    """
    for surface in surface_forms:
        if surface != surface.upper():  # has at least one lowercase letter
            return surface
    return surface_forms[0]


@router.get("/entities/search", response_model=EntitySearchResponse)
def search_entities(
    q: str = Query(..., min_length=1, description="Search phrase, Greek or English"),
    entity_class: str = Query(
        "course", alias="class", description="Entity type to search: 'course' or 'book'"
    ),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
) -> EntitySearchResponse:
    """Search KG entity titles by name, ranked by similarity to ``q``.

    Calls the exact same ``rank_titles`` function the SPARQL grounding
    pipeline uses (see module docstring) — no separate search logic to keep
    in sync.

    Returns 400 if ``class`` is not one of the supported values.
    """
    if entity_class not in _SUPPORTED_CLASSES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported class {entity_class!r}. Supported: {sorted(_SUPPORTED_CLASSES)}",
        )

    if entity_class == "book":
        # No book corpus yet — see ADR-018 "Deferred". Empty, not an error,
        # so the frontend can treat this the same as "no matches" rather
        # than a failure state.
        return EntitySearchResponse(query=q, results=[], total=0)

    matches = rank_titles(q, k=limit)
    results = [
        EntitySearchResult(title=_pick_display_surface(m.surface_forms), score=m.score)
        for m in matches
    ]
    return EntitySearchResponse(query=q, results=results, total=len(results))
