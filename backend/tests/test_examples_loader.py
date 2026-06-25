"""Tests for app.prompts.examples_loader."""

from __future__ import annotations


from app.prompts.examples_loader import (
    REQUIRED_FIELDS,
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

    def test_block_has_both_language_questions(self) -> None:
        block = select_few_shot(k=1)
        assert "Question (Greek):" in block
        assert "Question (English):" in block
