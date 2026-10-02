"""Tests for scripts/compare_runs.py — the paired comparison of two eval runs (ADR-038).

Two prompt versions answer the SAME items, so the right test looks only at the items that
flipped (McNemar, Dietterich 1998) and resamples items in pairs for F1 (paired bootstrap,
Berg-Kirkpatrick et al. 2012). scripts/ is not a package, so the module is loaded by path.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "scripts" / "compare_runs.py"


@pytest.fixture(scope="module")
def cmp():
    spec = importlib.util.spec_from_file_location("compare_runs", _PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _item(item_id: str, ok: bool, *, shown: bool = False, broken: bool = False) -> dict:
    return {
        "id": item_id,
        "result_match": None if broken else ok,
        "intent_match": None if broken else ok,
        "f1": None if broken else float(ok),
        "shown": shown,
        "broken_gold": broken,
    }


def test_flips_and_mcnemar(cmp) -> None:
    """The todo's example: 5 gains / 2 losses → exact p = 58/128 ≈ 0.45 (not significant)."""
    a = [_item(f"g{i}", False) for i in range(5)] + [_item(f"l{i}", True) for i in range(2)]
    b = [_item(f"g{i}", True) for i in range(5)] + [_item(f"l{i}", False) for i in range(2)]
    a += [_item("same", True), _item("shown", False, shown=True), _item("broken", True, broken=True)]
    b += [_item("same", True), _item("shown", True, shown=True), _item("broken", True)]
    out = cmp.compare(a, b)
    assert out["n"] == 8  # shown and broken-gold items are not paired
    intent = out["intent"]
    assert intent["gains"] == [f"g{i}" for i in range(5)] and intent["losses"] == ["l0", "l1"]
    assert (intent["a"], intent["b"]) == (3, 6)
    assert intent["p"] == pytest.approx(58 / 128)
    assert out["f1"]["delta"] == pytest.approx(3 / 8)


def test_render_puts_the_headline_first(cmp) -> None:
    """Macro F1 QALD is the headline (ADR-038): its table comes before the pass/fail one."""
    text = cmp.render(cmp.compare([_item("x", True)], [_item("x", False)]), "A", "B")
    assert text.index("Macro F1 QALD") < text.index("Intent-based match")


def test_only_items_in_both_runs_are_paired(cmp) -> None:
    out = cmp.compare([_item("x", True), _item("y", True)], [_item("x", False)])
    assert out["n"] == 1 and out["intent"]["losses"] == ["x"]
    assert "x" in cmp.render(out, "A", "B")
