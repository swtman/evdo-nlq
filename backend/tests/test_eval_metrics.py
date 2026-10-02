"""Tests for app.evaluation.metrics — the three eval numbers of ADR-038.

  strict  — today's rule, unchanged (positional columns, "set" = multiset); kept so every
            report stays comparable with the reports written before ADR-038
  intent  — intent-based execution match (Floratou et al., CIDR 2024, §4): rows as a true
            set, gold columns matched to generated columns by CONTENT in any order, extra
            generated columns allowed; a "no" may be ASK false / empty SELECT / a zero count
  F1      — per-question precision/recall/F over answer sets with QALD-9's empty-answer
            rules ("Macro F1 QALD", CEUR-WS Vol-2241 p. 62)

Every case below is one of the real shapes S49 found in the live v9 run (ex-003/004 column
order, ex-011 extra column, ex-016/te-001 duplicates, te-042…046 "no" answers).
"""

from __future__ import annotations

import pytest

from app.evaluation.metrics import (
    answer_kind,
    content_mappings,
    f1_qald,
    failure_cause,
    intent_match,
    says_no,
    strict_match,
)
from app.sparql.client import SparqlResult


def res(columns: list[str], *rows: tuple, boolean: bool | None = None) -> SparqlResult:
    """A SparqlResult from positional row tuples (values as GraphDB returns them: strings)."""
    return SparqlResult(
        columns=columns, rows=[dict(zip(columns, r, strict=True)) for r in rows], boolean=boolean
    )


def ask(value: bool) -> SparqlResult:
    """What SparqlClient returns for an ASK query since ADR-037."""
    return res(["answer"], ("true" if value else "false",), boolean=value)


# ---------------------------------------------------------------------------
# strict — must stay exactly today's rule
# ---------------------------------------------------------------------------


class TestStrictUnchanged:
    def test_set_is_a_multiset(self) -> None:
        gold = res(["t"], ("A",), ("B",))
        assert strict_match(gold, res(["x"], ("B",), ("A",)), "set")
        assert not strict_match(gold, res(["x"], ("A",), ("B",), ("B",)), "set")

    def test_columns_are_positional(self) -> None:
        gold = res(["u", "n"], ("ΑΠΘ", "57"))
        assert not strict_match(gold, res(["n", "u"], ("57", "ΑΠΘ")), "scalar")

    def test_ordered_and_scalar(self) -> None:
        gold = res(["t"], ("A",), ("B",))
        assert strict_match(gold, res(["t"], ("A",), ("B",)), "ordered")
        assert not strict_match(gold, res(["t"], ("B",), ("A",)), "ordered")
        assert not strict_match(res(["n"], ("1",)), res(["n"], ("1",), ("1",)), "scalar")

    def test_none_compares_as_empty_string(self) -> None:
        assert strict_match(res(["a"], (None,)), res(["b"], ("",)), "set")

    def test_unknown_mode_raises(self) -> None:
        with pytest.raises(ValueError):
            strict_match(res(["a"]), res(["a"]), "fuzzy")


# ---------------------------------------------------------------------------
# answer kind and "no"
# ---------------------------------------------------------------------------


class TestAnswerKind:
    def test_zero_count_is_a_no(self) -> None:
        assert answer_kind(res(["courses"], ("0",)), "scalar") == "zero-or-no"

    def test_ask_false_gold_is_a_no(self) -> None:
        assert answer_kind(ask(False), "scalar") == "zero-or-no"

    def test_numeric_single_row_is_a_count(self) -> None:
        assert answer_kind(res(["n"], ("57",)), "scalar") == "count"
        assert answer_kind(res(["a", "b", "c"], ("57", "56", "86")), "scalar") == "count"

    def test_everything_else_is_a_list(self) -> None:
        assert answer_kind(res(["t"], ("Algorithms",)), "set") == "list"
        assert answer_kind(res(["t", "n"], ("A", "3"), ("B", "4")), "set") == "list"
        assert answer_kind(res(["t"]), "set") == "list"

    def test_not_answerable(self) -> None:
        assert answer_kind(None, "not-answerable") == "not-answerable"


class TestSaysNo:
    @pytest.mark.parametrize(
        "gen",
        [ask(False), res(["c", "t", "u"]), res([]), res(["n"], ("0",)), res(["a", "b"], ("0", ""))],
        ids=["ASK false", "empty SELECT", "no columns", "zero count", "zero and empty"],
    )
    def test_accepted_forms(self, gen: SparqlResult) -> None:
        assert says_no(gen)

    @pytest.mark.parametrize(
        "gen",
        [ask(True), res(["n"], ("3",)), res(["t"], ("A",)), res(["n"], ("0",), ("0",))],
        ids=["ASK true", "positive count", "a row", "two rows"],
    )
    def test_rejected_forms(self, gen: SparqlResult) -> None:
        assert not says_no(gen)


# ---------------------------------------------------------------------------
# content mapping and intent
# ---------------------------------------------------------------------------


class TestContentMappings:
    def test_maps_by_distinct_content(self) -> None:
        gold = res(["u", "n"], ("ΑΠΘ", "57"))
        gen = res(["n", "x", "u"], ("57", "zzz", "ΑΠΘ"))
        assert list(content_mappings(gold, gen)) == [("u", "n")]

    def test_no_mapping_with_too_few_columns(self) -> None:
        assert list(content_mappings(res(["a", "b"], ("1", "2")), res(["a"], ("1",)))) == []

    def test_two_columns_with_equal_content_give_both_mappings(self) -> None:
        gold = res(["a", "b"], ("1", "1"))
        gen = res(["x", "y"], ("1", "1"))
        assert sorted(content_mappings(gold, gen)) == [("x", "y"), ("y", "x")]


class TestIntentMatch:
    def test_duplicates_ignored(self) -> None:  # te-001: right 2 books ×3; ex-016: gold has duplicates
        gold = res(["t"], ("A",), ("B",))
        assert intent_match(gold, res(["x"], ("A",), ("B",), ("A",), ("B",), ("B",)), "set")
        assert intent_match(res(["t"], ("A",), ("A",)), res(["t"], ("A",)), "set")

    def test_column_order_ignored(self) -> None:  # ex-003
        gold = res(["u", "d", "c"], ("57", "56", "86"))
        assert intent_match(gold, res(["c", "u", "d"], ("86", "57", "56")), "scalar")

    def test_extra_generated_column_allowed(self) -> None:  # ex-011
        gold = res(["t", "n"], ("A", "1"), ("B", "2"))
        gen = res(["n", "t", "extra"], ("1", "A", "x"), ("2", "B", "y"))
        assert intent_match(gold, gen, "set")

    def test_too_few_columns_fails(self) -> None:
        assert not intent_match(res(["t", "n"], ("A", "1")), res(["t"], ("A",)), "set")

    def test_wrong_values_fail(self) -> None:
        assert not intent_match(res(["t"], ("A",), ("B",)), res(["t"], ("A",), ("C",)), "set")
        assert not intent_match(res(["t"], ("A",), ("B",)), res(["t"], ("A",)), "set")

    def test_rows_must_pair_up_not_only_columns(self) -> None:
        """Both columns hold the right VALUES, but paired wrongly — the mapping must not pass it."""
        gold = res(["u", "n"], ("ΑΠΘ", "57"), ("ΕΚΠΑ", "40"))
        gen = res(["u", "n"], ("ΑΠΘ", "40"), ("ΕΚΠΑ", "57"))
        assert not intent_match(gold, gen, "set")

    def test_ordered_keeps_order_of_distinct_rows(self) -> None:  # ex-004
        gold = res(["u", "n"], ("A", "3"), ("B", "2"))
        assert intent_match(gold, res(["n", "u"], ("3", "A"), ("3", "A"), ("2", "B")), "ordered")
        assert not intent_match(gold, res(["u", "n"], ("B", "2"), ("A", "3")), "ordered")

    def test_scalar_needs_one_distinct_row(self) -> None:
        gold = res(["n"], ("57",))
        assert intent_match(gold, res(["n"], ("57",), ("57",)), "scalar")
        assert not intent_match(gold, res(["n"], ("57",), ("56",)), "scalar")

    @pytest.mark.parametrize("gen", [ask(False), res(["c", "t", "u"]), res(["n"], ("0",))])
    def test_no_in_any_form(self, gen: SparqlResult) -> None:  # te-042…046
        assert intent_match(res(["courses"], ("0",)), gen, "scalar")

    def test_no_rule_rejects_a_list(self) -> None:  # te-047: lists where it IS taught
        assert not intent_match(res(["courses"], ("0",)), res(["u"], ("ΑΠΘ",)), "scalar")

    def test_empty_gold_needs_empty_answer(self) -> None:
        assert intent_match(res(["t"]), res(["x", "y"]), "set")
        assert not intent_match(res(["t"]), res(["x"], ("A",)), "set")

    @pytest.mark.parametrize(
        ("gold", "gen", "mode"),
        [
            (res(["t"], ("A",), ("B",)), res(["x"], ("B",), ("A",)), "set"),
            (res(["t"], ("A",), ("B",)), res(["x"], ("A",), ("B",)), "ordered"),
            (res(["n"], ("0",)), res(["m"], ("0",)), "scalar"),
            (res(["n", "m"], ("1", "2")), res(["a", "b"], ("1", "2")), "scalar"),
        ],
    )
    def test_strict_pass_implies_intent_pass(self, gold, gen, mode) -> None:
        assert strict_match(gold, gen, mode) and intent_match(gold, gen, mode)


# ---------------------------------------------------------------------------
# macro F1 QALD — per-question P/R/F
# ---------------------------------------------------------------------------


class TestF1Qald:
    def test_qald_empty_rules(self) -> None:
        empty_gold = res(["t"])
        assert f1_qald(empty_gold, res(["t"]), "set") == (1.0, 1.0, 1.0)
        assert f1_qald(empty_gold, res(["t"], ("A",)), "set") == (0.0, 0.0, 0.0)
        # gold has answers, system gives none → "cannot answer": P = 1, R = F = 0 (Macro F1 QALD)
        assert f1_qald(res(["t"], ("A",)), res(["t"]), "set") == (1.0, 0.0, 0.0)

    def test_failed_generation_is_an_empty_answer(self) -> None:
        assert f1_qald(res(["t"], ("A",)), None, "set") == (1.0, 0.0, 0.0)

    def test_failed_generation_never_earns_credit_on_an_empty_gold(self) -> None:
        """Deviation from a literal reading of QALD-9, stated in ADR-038: an error is not a
        correct empty answer."""
        assert f1_qald(res(["t"]), None, "set") == (0.0, 0.0, 0.0)

    def test_partial_credit(self) -> None:
        gold = res(["t"], *[(f"B{i}",) for i in range(10)])
        gen = res(["t"], *[(f"B{i}",) for i in range(8)])
        p, r, f = f1_qald(gold, gen, "set")
        assert (p, r) == (1.0, 0.8) and f == pytest.approx(2 * 0.8 / 1.8)

    def test_wrong_extra_rows_lower_precision(self) -> None:
        gold = res(["t"], ("A",), ("B",))
        p, r, _ = f1_qald(gold, res(["t"], ("A",), ("B",), ("C",), ("D",)), "set")
        assert (p, r) == (0.5, 1.0)

    def test_best_mapping_used_with_extra_columns(self) -> None:
        gold = res(["t"], ("A",), ("B",))
        gen = res(["n", "t"], ("1", "A"), ("2", "Z"))
        assert f1_qald(gold, gen, "set") == (0.5, 0.5, 0.5)

    def test_no_overlapping_column_is_zero(self) -> None:
        assert f1_qald(res(["t"], ("A",)), res(["t"], ("Z",)), "set") == (0.0, 0.0, 0.0)

    def test_no_items_are_binary(self) -> None:
        gold = res(["courses"], ("0",))
        assert f1_qald(gold, ask(False), "scalar") == (1.0, 1.0, 1.0)
        assert f1_qald(gold, res(["u"], ("ΑΠΘ",)), "scalar") == (0.0, 0.0, 0.0)

    def test_order_is_ignored(self) -> None:
        gold = res(["t"], ("A",), ("B",))
        assert f1_qald(gold, res(["t"], ("B",), ("A",)), "ordered") == (1.0, 1.0, 1.0)


# ---------------------------------------------------------------------------
# failure causes (the report's error-analysis section)
# ---------------------------------------------------------------------------


class TestFailureCause:
    def cause(self, gold, gen, mode="set", error=None):
        strict = gen is not None and strict_match(gold, gen, mode)
        intent = gen is not None and intent_match(gold, gen, mode)
        f = f1_qald(gold, gen, mode)[2]
        return failure_cause(gold, gen, mode, strict=strict, intent=intent, f1=f, error=error)

    def test_pass_has_no_cause(self) -> None:
        assert self.cause(res(["t"], ("A",)), res(["t"], ("A",))) is None

    def test_metric_artefacts(self) -> None:
        assert self.cause(res(["courses"], ("0",)), ask(False), "scalar") == '"none" form'
        two = res(["t", "n"], ("A", "1"))
        assert self.cause(two, res(["n", "t", "x"], ("1", "A", "q"))) == "extra columns"
        assert self.cause(res(["t"], ("A",)), res(["t"], ("A",), ("A",))) == "duplicate rows"
        assert self.cause(two, res(["n", "t"], ("1", "A")), "scalar") == "column order"

    def test_real_failures(self) -> None:
        gold = res(["t", "n"], ("A", "1"), ("B", "2"))
        assert self.cause(gold, None, error="pipeline error") == "pipeline error"
        assert self.cause(gold, None, error="execution error") == "execution error"
        assert self.cause(gold, None, error="said not answerable") == "said not answerable"
        assert self.cause(gold, res(["t"], ("A",))) == "too few columns"
        assert self.cause(gold, res(["t", "n"])) == "empty answer"
        assert self.cause(gold, res(["t", "n"], ("A", "1"))) == "wrong rows (partial)"
        assert self.cause(gold, res(["t", "n"], ("Z", "9"))) == "wrong rows"
