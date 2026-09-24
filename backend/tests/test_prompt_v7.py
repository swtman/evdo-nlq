"""Tests for prompt nl-to-sparql-v7 (branch feat/prompt-v7-answer-entity).

v7 forks v6 and rewrites Rule 13 around the ANSWER ENTITY (the noun the question
asks "which …" about): it fixes the level of every NOT / BOTH condition and the
shape of every result row, repeats the year inside filters, uses unquoted
integer codes, and adds a worked example built from books and a year that do
not occur in the eval set. Evidence: the first live v6 eval, where all 5 real
errors applied a set condition per course while the question asked about
departments or universities.
"""

import re
from pathlib import Path

import yaml

from app.prompts.loader import load, load_user_template
from app.sparql.client import validate_sparql

_EXAMPLES = Path(__file__).resolve().parents[2] / "prompts" / "examples.yaml"
_WORKED_EXAMPLE_CODES = ("59359780", "13898")


def test_v7_keeps_v6_slot_layout() -> None:
    """Same cacheable layout as v6 (ADR-026): static system, hints in the user message."""
    system = load("nl-to-sparql", 7)
    assert "{ontology_summary}" in system and "{few_shot_block}" in system
    assert "{grounding_hints}" not in system
    assert load_user_template("nl-to-sparql", 7) == load_user_template("nl-to-sparql", 6)


def test_v7_rule13_is_about_the_answer_entity() -> None:
    system = load("nl-to-sparql", 7)
    rule13 = system[system.index("13. ") : system.index("14. ")]
    for phrase in ("answer entity", "Ποια Τμήματα", "Ποια Πανεπιστήμια", "FILTER EXISTS",
                   "FILTER NOT EXISTS", "evdx:year", "one row per answer entity"):
        assert phrase in rule13, phrase


def test_v7_never_quotes_a_book_code() -> None:
    """Rule 15: codes are integers — a quoted code matches zero triples. v6's Rule 13
    examples contradicted this with evdx:hasCode "X"."""
    assert not re.search(r'hasCode\s+"', load("nl-to-sparql", 7))


def test_v7_full_sparql_examples_are_valid() -> None:
    blocks = re.findall(r"```sparql\n(.*?)```", load("nl-to-sparql", 7), re.DOTALL)
    full_queries = [b for b in blocks if "SELECT" in b and "PREFIX" in b]
    assert full_queries  # the worked example is there
    for query in full_queries:
        assert validate_sparql(query) is None, query[:80]


def test_worked_example_does_not_leak_into_the_eval_set() -> None:
    """The worked example must not reveal any eval answer: its books must not occur
    in any question or gold query of examples.yaml."""
    examples = yaml.safe_load(_EXAMPLES.read_text(encoding="utf-8"))["examples"]
    for ex in examples:
        text = " ".join(str(ex.get(k, "")) for k in ("question_greek", "question_english", "gold_sparql"))
        for code in _WORKED_EXAMPLE_CODES:
            assert code not in text, (ex["id"], code)


def test_v6_still_loadable_for_ab() -> None:
    assert "Resolved entities" in load("nl-to-sparql", 6)
