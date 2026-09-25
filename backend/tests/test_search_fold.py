"""ΟΝΤΟΛΟΓΙΑ page search — word folding and lexicon (ADR-030, plan step 1).

``normalize.search_fold`` / ``search_words`` turn a department/university name (index time)
and a typed query (search time) into the same words, so the word rules can compare them.
The behaviour is pinned to the S35 v2.2 prototype that was measured
(notes/investigations/title-linking/scripts/s35_word_search_rules.py) — the parity check
S37 relies on it.
"""

from __future__ import annotations

import pytest

from app.grounding.lexicon import (
    _SEARCH_CLASS_WORDS,
    _SEARCH_CONNECTORS,
    _SEARCH_LOOKALIKES,
    _SEARCH_OPTIONAL,
    _SEARCH_SYNONYMS,
)
from app.grounding.normalize import normalize_greek, search_fold, search_words


@pytest.mark.parametrize(
    ("raw", "words"),
    [
        # accents, case and final sigma folded like normalize_greek
        ("Νοσηλευτικής", ["νοσηλευτικησ"]),
        ("ΝΟΣΗΛΕΥΤΙΚΗΣ", ["νοσηλευτικησ"]),
        # the trailing "(…)" is KEPT — campus names are searchable (S33/S35)
        ("ΝΟΣΗΛΕΥΤΙΚΗΣ (ΛΑΡΙΣΑ)", ["νοσηλευτικησ", "λαρισα"]),
        # synonym: «&» is «και»
        ("ΕΜΠΟΡΙΑΣ & ΔΙΑΦΗΜΙΣΗΣ", ["εμποριασ", "και", "διαφημισησ"]),
        # synonym: the ΑΠΘ name abbreviates the city
        (
            "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ",
            ["αριστοτελειο", "πανεπιστημιο", "θεσσαλονικησ"],
        ),
        # dotted abbreviations joined, Greek and Latin look-alike letters
        ("ΜΗΧΑΝΟΛΟΓΩΝ ΜΗΧΑΝΙΚΩΝ Τ.Ε.", ["μηχανολογων", "μηχανικων", "τε"]),
        ("ΜΗΧΑΝΟΛΟΓΩΝ ΜΗΧΑΝΙΚΩΝ T.E.", ["μηχανολογων", "μηχανικων", "τε"]),
        # the query side types it without dots
        ("μηχανολογων μηχανικων τε", ["μηχανολογων", "μηχανικων", "τε"]),
        # punctuation separates words and is dropped
        ("ΔΙΟΙΚΗΣΗΣ, ΟΙΚΟΝΟΜΙΑΣ - ΕΠΙΚΟΙΝΩΝΙΑΣ", ["διοικησησ", "οικονομιασ", "επικοινωνιασ"]),
        ("", []),
        ("   ", []),
    ],
)
def test_search_words(raw: str, words: list[str]) -> None:
    assert search_words(raw) == words


@pytest.mark.parametrize(
    "raw",
    [
        "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ",
        "ΕΜΠΟΡΙΑΣ & ΔΙΑΦΗΜΙΣΗΣ",
        "ΠΟΛΙΤΙΚΩΝ ΜΗΧΑΝΙΚΩΝ Τ.Ε. (ΛΑΡΙΣΑ)",
    ],
)
def test_search_fold_is_stable(raw: str) -> None:
    """Folding an already folded text changes nothing (index and query agree)."""
    once = search_fold(raw)
    assert search_fold(once) == once


def test_lexicon_entries_are_in_normalized_form() -> None:
    """Every entry is stored folded — an accented or «ς» entry would never match."""
    for word in _SEARCH_CONNECTORS | _SEARCH_CLASS_WORDS | set(_SEARCH_LOOKALIKES.values()):
        assert normalize_greek(word) == word, word
    for key in _SEARCH_SYNONYMS:
        assert normalize_greek(key, strip_status_suffix=False) == key, key


def test_optional_words_are_connectors_and_class_words() -> None:
    assert _SEARCH_OPTIONAL == _SEARCH_CONNECTORS | _SEARCH_CLASS_WORDS
    assert not (_SEARCH_CONNECTORS & _SEARCH_CLASS_WORDS)
    assert {"και", "του", "τησ"} <= _SEARCH_CONNECTORS
    assert {"τμημα", "σχολη", "ιδρυμα"} <= _SEARCH_CLASS_WORDS
