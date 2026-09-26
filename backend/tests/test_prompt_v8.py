"""Tests for prompt nl-to-sparql-v8 (branch feat/snowball-stemmer, ADR-031).

v8 forks v7 and changes ONE thing (user decision Q1): the "Topic stems" bullet of
Rule 16. Each stem line now reads `- stem → pattern` and the model is told to use
the pattern in FILTER(REGEX(LCASE(?var), "pattern")) — one vowel class per vowel,
so accent-free ALL-CAPS and accented mixed-case titles match with one filter
(C5: the old `stem | stém` pair accented only the last vowel).

The three few-shot demos that use topic stems (ex-024, ex-025, ex-026 — Examples
5, 2 and 3 of every system prompt) must teach the same format.
"""

import re
from pathlib import Path

import yaml

from app.grounding.stem import stem_pattern
from app.pipeline.query_pipeline import PROMPT_VERSION
from app.prompts.loader import load, load_user_template
from app.sparql.client import validate_sparql

_EXAMPLES = Path(__file__).resolve().parents[2] / "prompts" / "examples.yaml"


def _examples() -> dict[str, dict]:
    return {e["id"]: e for e in yaml.safe_load(_EXAMPLES.read_text(encoding="utf-8"))["examples"]}


def _topic_stems_bullet(version: int) -> str:
    """The Rule 16 bullet itself — not the earlier mention «use the **Topic stems** instead»."""
    system = load("nl-to-sparql", version)
    start = system.index("- **Topic stems**:")
    return system[start : system.index("\n", start)]


def test_production_prompt_is_v8() -> None:
    assert PROMPT_VERSION == 8


def test_v8_keeps_v7_slot_layout() -> None:
    """Same cacheable layout as v6/v7 (ADR-026): static system, hints in the user message."""
    system = load("nl-to-sparql", 8)
    assert "{ontology_summary}" in system and "{few_shot_block}" in system
    assert "{grounding_hints}" not in system
    assert load_user_template("nl-to-sparql", 8) == load_user_template("nl-to-sparql", 7)


def test_v8_topic_stems_use_the_regex_pattern() -> None:
    bullet = _topic_stems_bullet(8)
    assert "REGEX(LCASE(" in bullet
    assert f"αλγοριθμ → {stem_pattern('αλγοριθμ')}" in bullet  # the example matches the code
    assert "αλγορ | αλγόρ" not in bullet


def test_v8_changes_only_the_topic_stems_bullet() -> None:
    """Q1: v8 = v7 + the stem change. Outside that bullet and the front matter /
    'What changed' notes, the system text is identical to v7."""

    def core(version: int) -> str:
        system = load("nl-to-sparql", version)
        return system.replace(_topic_stems_bullet(version), "")

    assert core(8) == core(7)


def test_v8_full_sparql_examples_are_valid() -> None:
    blocks = re.findall(r"```sparql\n(.*?)```", load("nl-to-sparql", 8), re.DOTALL)
    for query in (b for b in blocks if "SELECT" in b and "PREFIX" in b):
        assert validate_sparql(query) is None, query[:80]


def test_v7_still_loadable_for_ab() -> None:
    assert "αλγορ | αλγόρ" in load("nl-to-sparql", 7)


def test_stem_demos_teach_the_v8_format() -> None:
    """The few-shot demos use REGEX with the code's own patterns — never the old
    CONTAINS stem pair — and stay valid SPARQL."""
    examples = _examples()
    patterns = {
        "ex-024": stem_pattern("αλγοριθμ"),
        "ex-025": stem_pattern("θρησκευτ"),
        "ex-026": stem_pattern("θρησκευτ"),
    }
    for ex_id, pattern in patterns.items():
        gold = examples[ex_id]["gold_sparql"]
        assert "REGEX(LCASE(?" in gold and f'"{pattern}"' in gold, ex_id
        assert 'CONTAINS(LCASE(?bt), "' not in gold, ex_id
        assert validate_sparql(gold) is None, ex_id


def test_ex025_binds_the_university_its_question_names() -> None:
    """Gold fix (ADR-031): the question says «Πανεπιστήμιο Πειραιώς» but the SPARQL
    bound ΟΙΚΟΝΟΜΙΚΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΑΘΗΝΩΝ — a wrong name mapping shown in every prompt."""
    ex = _examples()["ex-025"]
    assert "Πειραιώς" in ex["question_greek"]
    assert '"ΠΑΝΕΠΙΣΤΗΜΙΟ ΠΕΙΡΑΙΩΣ"' in ex["gold_sparql"]
    assert "ΟΙΚΟΝΟΜΙΚΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΑΘΗΝΩΝ" not in ex["gold_sparql"]
