"""Word search for the ΟΝΤΟΛΟΓΙΑ page — universities and departments (ADR-030).

WHY A SECOND SEARCH, BESIDE ``rank_titles``
-------------------------------------------
Two different jobs. ``rank_titles`` (and ``linker.py``) LINK a name mentioned inside a
question for the LLM: they must be strict, because a wrong binding silently changes the
SPARQL. The ΟΝΤΟΛΟΓΙΑ page is a person LOOKING a name up: it must find what they type
(a word from the middle of a name, a campus in the "(…)", an acronym, a typo) and show
everything that could be meant. Both read the same ``entities.db`` rows and the same
normalization; only the matching policy differs. Grounding is unchanged by this module.

THE RULES (measured: S35 v2.2 in notes/investigations/title-linking/; parity: S38)
-------------------------------------------------------------------------------------
Names and the query are folded by ``normalize.search_words`` (accents, case, final
sigma; "(…)" kept; «&»=«και», «θεσ/νικησ»=«θεσσαλονικησ», «Τ.Ε.»=«τε»). Then:

* every typed word must match a word of ONE exact name, as
    exact  — the same word;
    start  — the start of a word            («νοσηλ» -> νοσηλευτικησ);
    typo   — Levenshtein <= 1 for typed words of 5+ letters, <= 2 for 8+;
  never inside a longer word («αγωγης» does not match «παραγωγης»);
* connectors in names («και», «του» …) match only as whole words («κα» ≠ «και»);
* optional typed words (connectors + class words: «τμήμα», «σχολή» …) need not match,
  unless the query has nothing else;
* university acronyms (``gazetteer.ACRONYM_MAP``) are whole-name aliases;
* fewer than ``MIN_QUERY_LETTERS`` letters -> no results (the page shows its prompt).

Ranking (lower is better), per exact name; a result (all names sharing one group key)
takes its best name's rank:
  -1  the typed text IS the name, literally        («ΑΝΑΚΑΙΝΙΣΗΣ ΚΑΙ …» vs «… & …»)
   0  the name's words equal the typed words (after synonyms), or an acronym
   1/2/3  otherwise the WORST typed word's match: exact / start / typo
then: total typos, fewer words in the name, the name, the group key.

HOW (SQLite FTS5 + a small rules layer)
---------------------------------------
Each typed word is expanded against ``{class}_vocab`` into the vocabulary words it may
match; FTS5 (``{class}_name_fts``) returns the names containing, for EVERY typed word,
one of its expansions; the ranking above runs in Python on those candidates. Words are
passed to FTS5 only as quoted terms built from ``search_words`` output, so FTS5 query
syntax in the input (``*``, ``"``, ``NEAR``, ``OR`` …) is inert.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from rapidfuzz.distance import Levenshtein

from app.grounding import db
from app.grounding.gazetteer import ACRONYM_MAP
from app.grounding.lexicon import _SEARCH_OPTIONAL
from app.grounding.normalize import normalize_greek, search_words
from app.grounding.schema import SEARCH_CLASSES
from app.grounding.title_index.corpus import _IndexState, _lookup_surfaces_and_parents
from app.grounding.title_index.policy import TitleMatch

# The page shows results from the 2nd letter on (user decision, 2026-09-25): one letter
# matches the start of ~55 department words on average (S35 M5).
MIN_QUERY_LETTERS: int = 2

# Match levels of one typed word against one name word (lower is better).
_EXACT, _START, _TYPO = 1, 2, 3

# TitleMatch.score for each rank tier — a coarse indicator only (the page orders by the
# full rank key, not by this number).
_TIER_SCORE: dict[int, float] = {-1: 1.0, 0: 1.0, _EXACT: 0.9, _START: 0.8, _TYPO: 0.7}


def _typo_budget(word: str) -> int:
    """Edits allowed for a typed word: 1 from 5 letters, 2 from 8 (S35)."""
    return 2 if len(word) >= 8 else 1 if len(word) >= 5 else 0


@dataclass(frozen=True)
class _Name:
    """One exact name row of ``{class}_name``."""

    norm: str  # group key
    surface: str  # raw KG literal
    words: tuple[str, ...]


def _expand(word: str, vocab: dict[str, bool]) -> dict[str, tuple[int, int]]:
    """Vocabulary words a typed word may match -> (level, typos).

    Args:
        word: One folded typed word.
        vocab: Every name word of the class -> whether it is a connector.
    """
    budget = _typo_budget(word)
    out: dict[str, tuple[int, int]] = {}
    for w, is_connector in vocab.items():
        if w == word:
            out[w] = (_EXACT, 0)
        elif is_connector:
            continue  # connectors match only whole
        elif w.startswith(word):
            out[w] = (_START, 0)
        elif budget and abs(len(w) - len(word)) <= budget:
            d = Levenshtein.distance(w, word, score_cutoff=budget)
            if d <= budget:
                out[w] = (_TYPO, d)
    return out


def _fts_query(expansions: list[dict[str, tuple[int, int]]]) -> str:
    """AND over typed words of (OR over that word's expansions), every term quoted."""
    return " AND ".join(
        "(" + " OR ".join('"' + w.replace('"', '""') + '"' for w in sorted(e)) + ")"
        for e in expansions
    )


def _aliases(entity_class: str) -> dict[str, str]:
    """Folded acronym -> group key (universities only)."""
    if entity_class != "university":
        return {}
    return {" ".join(search_words(a)): normalize_greek(c) for a, c in ACRONYM_MAP.items()}


def _search(
    conn: sqlite3.Connection, phrase: str, *, entity_class: str, limit: int, offset: int
) -> tuple[list[TitleMatch], int]:
    """The word search on an open connection (see module docstring).

    Args:
        conn: Connection with ``row_factory = sqlite3.Row`` and the word index built
              (``schema.sync_search_index``).
        phrase: What the user typed.
        entity_class: One of ``schema.SEARCH_CLASSES``.
        limit: Page size.
        offset: Number of ranked results to skip.

    Returns:
        ``(page, total)`` — the ranked results ``[offset, offset + limit)`` and the
        number of all results.

    Raises:
        ValueError: If ``entity_class`` has no word index.
    """
    if entity_class not in SEARCH_CLASSES:
        raise ValueError(f"{entity_class!r} has no word search; only {list(SEARCH_CLASSES)} do")

    words = search_words(phrase)
    if len("".join(words)) < MIN_QUERY_LETTERS:
        return [], 0
    typed = " ".join(words)
    literal = normalize_greek(phrase, strip_status_suffix=False)
    required = [w for w in words if w not in _SEARCH_OPTIONAL] or words

    vocab = {
        r["word"]: bool(r["is_connector"])
        for r in conn.execute(f"SELECT word, is_connector FROM {entity_class}_vocab")
    }
    expansions = [_expand(w, vocab) for w in required]

    candidates: list[_Name] = []
    if all(expansions):
        rows = conn.execute(
            f"SELECT n.norm, n.surface, n.words FROM {entity_class}_name_fts f "
            f"JOIN {entity_class}_name n ON n.id = f.rowid WHERE {entity_class}_name_fts MATCH ?",
            (_fts_query(expansions),),
        )
        candidates = [_Name(r["norm"], r["surface"], tuple(r["words"].split())) for r in rows]

    best: dict[str, tuple] = {}
    for name in candidates:
        if normalize_greek(name.surface, strip_status_suffix=False) == literal:
            key: tuple = (-1, 0, 0, "", name.norm)
        elif " ".join(name.words) == typed:
            key = (0, 0, len(name.words), typed, name.norm)
        else:
            per_word = [min((e[w] for w in name.words if w in e), default=None) for e in expansions]
            if any(p is None for p in per_word):
                continue  # the words sit in different names of the row set — not one name
            key = (
                max(p[0] for p in per_word),
                sum(p[1] for p in per_word),
                len(name.words),
                " ".join(name.words),
                name.norm,
            )
        if name.norm not in best or key < best[name.norm]:
            best[name.norm] = key
    alias = _aliases(entity_class).get(typed)
    if alias is not None:
        best[alias] = (0, 0, 0, "", alias)

    ranked = sorted(best.items(), key=lambda kv: kv[1])
    state = _IndexState(conn=conn, table=entity_class)
    page: list[TitleMatch] = []
    for norm, key in ranked[offset : offset + limit]:
        surface_forms, parents, variants = _lookup_surfaces_and_parents(state, norm)
        page.append(
            TitleMatch(
                normalized_title=norm,
                score=_TIER_SCORE[key[0]],
                surface_forms=surface_forms,
                entity_class=entity_class,
                parents=parents,
                variants=variants,
            )
        )
    return page, len(ranked)


def search_names(
    phrase: str, *, entity_class: str, limit: int, offset: int = 0
) -> tuple[list[TitleMatch], int]:
    """Search the committed ``entities.db`` (see ``_search``).

    Opens a fresh read-only connection for the call, like ``rank_titles``.
    """
    conn = db.get_connection()
    try:
        return _search(conn, phrase, entity_class=entity_class, limit=limit, offset=offset)
    finally:
        conn.close()
