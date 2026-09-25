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

LOOKUP IS NOT LINKING (ADR-030)
-------------------------------
The two share the data (``entities.db``) and the normalization, not the matching
policy. Grounding LINKS a name inside a question and must be strict (a wrong binding
silently changes the SPARQL). This page is a person LOOKING a name up and must find
what they type and show everything that could be meant. So:

* course/book search here calls ``title_index.search.rank_titles`` — the same function
  ``hints.py`` uses for title candidates (their page matching gets its own measured
  branch later);
* university/department search here calls ``title_index.word_search.search_names`` —
  word rules measured in S35 and checked for parity in S38 — while grounding keeps
  ``linker.py``. One result list serves both the card (its first 8) and the «δείτε και
  τα N» modal (all of it, one scrollable list — ``limit`` up to 1000; ``total`` = every
  match), so the two views cannot disagree. ``offset`` is available for paging clients.

Every class needs at least ``MIN_QUERY_LETTERS`` (2) letters; below that the response
is empty, not an error — the page shows its prompt.

SCOPE
-----
All four classes in ``schema.TITLE_CLASSES`` — ``course``, ``book``,
``university``, ``department`` — return real, live-ranked results from
``GET /entities/search``. Each is matched by a different policy tuned to how
that class is actually typed (see ``title_index.policy._POLICY`` and ADR-020): a
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

from app.grounding.normalize import drop_status_suffix, search_words
from app.grounding.schema import LISTABLE_CLASSES, SEARCH_CLASSES, TITLE_CLASSES
from app.grounding.title_index import TitleMatch, list_titles, rank_titles
from app.grounding.title_index.word_search import MIN_QUERY_LETTERS, search_names

router = APIRouter()


class DepartmentVariant(BaseModel):
    """One exact department name inside a result, with its own universities.

    Fields
    ------
    name : str
        The exact KG name (whitespace collapsed for display only), e.g.
        "ΝΟΣΗΛΕΥΤΙΚΗΣ (ΑΛΕΞΑΝΔΡΟΥΠΟΛΗ)" — the string a SPARQL query must use.
    parents : list[str]
        The universities that have a department with exactly this name.
    literal : str
        The same name exactly as stored in the KG — whitespace untouched (the ⧉ copy
        and the «ακριβής μορφή» view of the ΟΝΤΟΛΟΓΙΑ page, ADR-030 C2).
    """

    name: str
    parents: list[str]
    literal: str


class EntitySearchResult(BaseModel):
    """One ranked (or, from ``/entities/list``, alphabetically listed) result.

    Fields
    ------
    title : str
        A display-ready surface form of the matched entity (the mixed-case
        accented KG variant when one exists, otherwise whatever form is
        stored). See ``_pick_display_surface``. For a department result that
        groups several exact names, the shared name without its trailing
        "(…)" — see ``_result``.
    score : float
        Similarity score in [0, 1], from ``TitleMatch.score``. Higher means
        a closer match to the query phrase. Always ``1.0`` for
        ``/entities/list`` results (listing implies no similarity judgement).
    parents : list[str]
        Parent university name(s) — populated only for
        ``class=department`` results; ``[]`` for every other class. A
        department name shared by several universities (a common name, or a
        joint programme) has more than one parent. Kept for compatibility;
        ``variants`` says which university has which exact name.
    variants : list[DepartmentVariant]
        ``class=department`` only: every exact name in this result, each with
        its own universities, in name order. ``[]`` for every other class.
        Needed because a result groups names that differ only by a trailing
        "(…)" — ΝΟΣΗΛΕΥΤΙΚΗΣ, ΝΟΣΗΛΕΥΤΙΚΗΣ (ΑΛΕΞΑΝΔΡΟΥΠΟΛΗ), … — and showing
        one of them hid the others (ADR-029).
    literals : list[str]
        Every KG literal of this result exactly as stored (all spelling variants, first
        occurrence order, duplicates removed) — ``title`` is a tidied display form, these
        are what a hand-written SPARQL query must use (ADR-030 C2). 13,301 course titles
        differ from their display form only by invisible whitespace.
    """

    title: str
    score: float
    parents: list[str] = []
    variants: list[DepartmentVariant] = []
    literals: list[str] = []


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


def _result(m: TitleMatch) -> EntitySearchResult:
    """Build one API result from a ``TitleMatch`` (shared by search and list).

    Departments carry ``variants`` — every exact name with its own
    universities. When a result groups SEVERAL names, its title is the shared
    name without the trailing "(…)" (``normalize.drop_status_suffix``, the
    same rule that formed the group key), so the card header reads
    "ΠΡΟΓΡΑΜΜΑ ΣΠΟΥΔΩΝ ΝΟΣΗΛΕΥΤΙΚΗΣ" above "… (ΛΑΜΙΑ)" and "… (ΛΑΡΙΣΑ)"
    instead of one of them hiding the other. A single name keeps its exact
    form as the title — nothing is shortened when nothing is grouped.
    """
    title = _pick_display_surface(m.surface_forms)
    if len(m.variants) > 1:
        title = drop_status_suffix(title)
    variants = [
        DepartmentVariant(name=" ".join(name.split()), parents=parents, literal=name)
        for name, parents in m.variants.items()
    ]
    return EntitySearchResult(
        title=title,
        score=m.score,
        parents=m.parents,
        variants=variants,
        literals=list(dict.fromkeys(m.surface_forms)),
    )


@router.get("/entities/search", response_model=EntitySearchResponse)
def search_entities(
    q: str = Query(..., min_length=1, description="Search phrase, Greek or English"),
    entity_class: str = Query(
        "course",
        alias="class",
        description="Entity type to search: 'course', 'book', 'university', or 'department'",
    ),
    # Up to 1000, like /entities/list: the ΟΝΤΟΛΟΓΙΑ modal shows ALL results of a query
    # in one scrollable list (ADR-030); the card asks for its first 8.
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of ranked results to skip"),
) -> EntitySearchResponse:
    """Search KG entity names by phrase (see module docstring "LOOKUP IS NOT LINKING").

    university/department: the word search, sliced by ``offset``/``limit``, with
    ``total`` = every match — the card shows the first 8, the modal the whole SAME list.
    course/book: ``rank_titles`` ranking as before; ``total`` counts the
    ranked matches up to ``offset + limit``. Fewer than ``MIN_QUERY_LETTERS`` letters:
    empty response for every class. The response shape is the same for all classes.

    Returns 400 if ``class`` is not one of the supported values.
    """
    if entity_class not in TITLE_CLASSES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported class {entity_class!r}. Supported: {sorted(TITLE_CLASSES)}",
        )
    if len("".join(search_words(q))) < MIN_QUERY_LETTERS:
        return EntitySearchResponse(query=q, results=[], total=0)

    if entity_class in SEARCH_CLASSES:
        matches, total = search_names(q, entity_class=entity_class, limit=limit, offset=offset)
    else:
        ranked = rank_titles(q, k=offset + limit, entity_class=entity_class)
        matches, total = ranked[offset:], len(ranked)
    return EntitySearchResponse(query=q, results=[_result(m) for m in matches], total=total)


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
    results = [_result(m) for m in matches]
    return EntitySearchResponse(query="", results=results, total=len(results))
