"""Tests for app.prompts.examples_loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.prompts.examples_loader import (
    REQUIRED_FIELDS,
    few_shot_ids,
    load_examples,
    select_few_shot,
)


class TestLoadExamples:
    def test_loads_without_error(self) -> None:
        examples = load_examples()
        assert len(examples) > 0

    def test_all_required_fields_present(self) -> None:
        examples = load_examples()
        for ex in examples:
            missing = REQUIRED_FIELDS - ex.keys()
            assert not missing, f"{ex.get('id', '?')} missing: {missing}"

    def test_ids_are_unique(self) -> None:
        examples = load_examples()
        ids = [ex["id"] for ex in examples]
        assert len(ids) == len(set(ids))

    def test_comparison_mode_values(self) -> None:
        valid = {"set", "ordered", "scalar", "not-answerable"}
        for ex in load_examples():
            assert ex["comparison_mode"] in valid, (
                f"{ex['id']} has invalid comparison_mode: {ex['comparison_mode']!r}"
            )

    def test_query_shape_values(self) -> None:
        valid = {
            "traversal-lookup",
            "book-course-flat-join",
            "book-course-group-concat",
            "multi-level-count",
            "multi-level-aggregate-with-concat",
            "set-difference-by-year",
            "set-difference-by-book",
            "set-intersection-by-book",
            "negative-existence",
            "ranking-by-count",
            "multi-book-comparison",
            "not-answerable",
            "alias-resolution",
            "topic-stem-match",
        }
        for ex in load_examples():
            assert ex["query_shape"] in valid, (
                f"{ex['id']} has unknown query_shape: {ex['query_shape']!r}"
            )

    def test_not_answerable_examples_have_comment_sparql(self) -> None:
        for ex in load_examples():
            if ex["query_shape"] == "not-answerable":
                assert ex["gold_sparql"].strip().startswith("# NOT_ANSWERABLE"), (
                    f"{ex['id']}: not-answerable example must start with # NOT_ANSWERABLE"
                )

    def test_caching_returns_same_object(self) -> None:
        first = load_examples()
        second = load_examples()
        assert first is second


class TestSelectFewShot:
    def test_returns_string(self) -> None:
        block = select_few_shot(k=6)
        assert isinstance(block, str)
        assert len(block) > 0

    def test_respects_k_limit(self) -> None:
        block = select_few_shot(k=3)
        # Each example block starts with "### Example N"
        count = block.count("### Example ")
        assert count <= 3

    def test_one_example_per_shape(self) -> None:
        """select_few_shot must not return two examples with the same query_shape."""
        block = select_few_shot(k=10)
        examples = load_examples()
        shapes_in_block: list[str] = []
        for ex in examples:
            if ex["query_shape"] not in shapes_in_block and f"{ex['query_shape']}" in block:
                shapes_in_block.append(ex["query_shape"])
        assert len(shapes_in_block) == len(set(shapes_in_block))

    def test_contains_sparql_prefix(self) -> None:
        block = select_few_shot(k=6)
        assert "PREFIX evdx:" in block

    def test_exclude_not_answerable(self) -> None:
        block = select_few_shot(k=10, include_not_answerable=False)
        assert "NOT_ANSWERABLE" not in block

    def test_includes_not_answerable_by_default(self) -> None:
        block = select_few_shot(k=10, include_not_answerable=True)
        assert "NOT_ANSWERABLE" in block

    def test_block_has_only_the_greek_question(self) -> None:
        """Users ask in Greek only (ADR-033): one "Question:" line per example — the English
        translation no longer takes space in every system prompt."""
        block = select_few_shot(k=8)
        assert block.count("Question: ") == block.count("### Example ")
        assert "Question (English)" not in block
        assert "Question (Greek)" not in block


class TestFewShotIds:
    """few_shot_ids(k) names the examples select_few_shot(k) shows — the eval leaves them out of
    its headline numbers (leakage, ADR-038)."""

    @pytest.mark.parametrize("k", [3, 6, 8])
    def test_ids_are_exactly_the_rendered_examples(self, k: int) -> None:
        block = select_few_shot(k=k)
        rendered = [ex["id"] for ex in load_examples() if ex["question_greek"].strip() in block]
        assert sorted(few_shot_ids(k)) == sorted(rendered)
        assert len(few_shot_ids(k)) == block.count("### Example ")

    def test_production_k_today(self) -> None:
        """Measured 2026-10-02 (plan mode): these 8 are in every production prompt."""
        assert sorted(few_shot_ids(8)) == [
            "ex-001", "ex-002", "ex-015", "ex-019", "ex-023", "ex-024", "ex-025", "ex-026"
        ]


class TestGreekOnly:
    def test_english_question_is_not_required(self) -> None:
        assert "question_english" not in REQUIRED_FIELDS
        assert "question_greek" in REQUIRED_FIELDS

    def test_gold_files_carry_no_english_questions(self) -> None:
        """Both gold files are Greek-only (ADR-033) — the eval measures what users ask."""
        import yaml

        prompts = Path(__file__).resolve().parents[2] / "prompts"
        for name in ("examples.yaml", "eval-departments.yaml"):
            examples = yaml.safe_load((prompts / name).read_text(encoding="utf-8"))["examples"]
            assert not [ex["id"] for ex in examples if "question_english" in ex], name
