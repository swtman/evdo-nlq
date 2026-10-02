"""Tests for app.evaluation.stats — intervals and paired tests for eval reports (ADR-038).

Numbers checked by hand:
  Wilson 16/32 → 0.336–0.664 (the todo's "≈ 34–66%")
  McNemar exact, 5 gains / 2 losses → 2 · (C(7,0)+C(7,1)+C(7,2)) / 2^7 = 58/128 = 0.453
"""

from __future__ import annotations

import pytest

from app.evaluation.stats import bootstrap_ci, mcnemar_exact, paired_bootstrap, wilson


class TestWilson:
    def test_half(self) -> None:
        lo, hi = wilson(16, 32)
        assert lo == pytest.approx(0.336, abs=0.001) and hi == pytest.approx(0.664, abs=0.001)

    def test_edges_stay_inside_zero_one(self) -> None:
        lo, hi = wilson(0, 20)
        assert lo == 0.0 and 0.0 < hi < 0.2
        lo, hi = wilson(20, 20)
        assert 0.8 < lo < 1.0 and hi == pytest.approx(1.0)

    def test_no_items_is_uninformative(self) -> None:
        assert wilson(0, 0) == (0.0, 1.0)


class TestMcNemar:
    def test_v8_to_v9_titles_example(self) -> None:
        assert mcnemar_exact(5, 2) == pytest.approx(58 / 128)

    def test_symmetric_and_bounded(self) -> None:
        assert mcnemar_exact(2, 5) == mcnemar_exact(5, 2)
        assert mcnemar_exact(0, 0) == 1.0
        assert mcnemar_exact(3, 3) == 1.0

    def test_all_flips_one_way(self) -> None:
        assert mcnemar_exact(8, 0) == pytest.approx(2 / 256)


class TestBootstrap:
    def test_seeded_and_brackets_the_mean(self) -> None:
        values = [1.0, 0.0, 1.0, 0.5, 1.0, 0.0, 0.8, 1.0]
        a = bootstrap_ci(values, seed=1)
        assert a == bootstrap_ci(values, seed=1)
        assert a[0] <= sum(values) / len(values) <= a[1]

    def test_constant_values_have_no_spread(self) -> None:
        assert bootstrap_ci([1.0] * 5) == (1.0, 1.0)

    def test_empty(self) -> None:
        assert bootstrap_ci([]) == (0.0, 0.0)


class TestPairedBootstrap:
    def test_identical_systems(self) -> None:
        delta, (lo, hi), p = paired_bootstrap([1.0, 0.0, 0.5], [1.0, 0.0, 0.5])
        assert delta == 0.0 and (lo, hi) == (0.0, 0.0) and p == 1.0

    def test_clear_gain_is_significant(self) -> None:
        a = [0.0] * 30
        b = [1.0] * 30
        delta, (lo, hi), p = paired_bootstrap(a, b, seed=3)
        assert delta == 1.0 and lo == hi == 1.0 and p < 0.01

    def test_lengths_must_match(self) -> None:
        with pytest.raises(ValueError):
            paired_bootstrap([1.0], [1.0, 0.0])
