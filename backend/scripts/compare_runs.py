"""Paired comparison of two eval runs on the same items (ADR-038).

WHY PAIRED?
-----------
Two prompt versions (or two models) answer the SAME questions. Comparing their two pass rates
as if they were independent samples throws that pairing away and needs far larger differences
to be convincing. A paired test looks only at what changed item by item:

- Intent and strict verdicts: the items that FLIPPED (fail → pass = gain, pass → fail = loss).
  Under "no difference" a flip is equally likely to go either way, so the exact McNemar test
  is a binomial test on the flips (Dietterich 1998). Example: v8 → v9 titles, 5 gains / 2
  losses → p ≈ 0.45 — a +3 that chance explains easily.
- Macro F1 (the headline): per-item F differences, resampled in pairs (paired bootstrap, Berg-Kirkpatrick et
  al. 2012) → the difference with a 95% interval and a p-value.

Items are paired by id. Items shown in the prompt (leakage) and broken-gold items are left
out, as in the reports' headline; so are items present in only one run.

Usage (from backend/; the inputs are the .json sidecars eval.py writes next to each report):
    uv run python scripts/compare_runs.py A.json B.json [--output comparison.md]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.evaluation.stats import mcnemar_exact, paired_bootstrap  # noqa: E402


def _usable(item: dict[str, Any]) -> bool:
    """Scored in the headline sense: gold executed and not shown in the prompt."""
    return item.get("result_match") is not None and not item.get("shown")


def _flips(pairs: list[tuple[dict, dict]], key: str) -> dict[str, Any]:
    """Pass counts of each run, gains/losses (ids) and the exact McNemar p for one verdict."""
    gains = [a["id"] for a, b in pairs if not a[key] and b[key]]
    losses = [a["id"] for a, b in pairs if a[key] and not b[key]]
    return {
        "a": sum(bool(a[key]) for a, _ in pairs),
        "b": sum(bool(b[key]) for _, b in pairs),
        "gains": gains,
        "losses": losses,
        "p": mcnemar_exact(len(gains), len(losses)),
    }


def compare(a_items: list[dict[str, Any]], b_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Pair two runs' item records by id and compare them (pure function — see module docstring).

    Returns {"n", "intent", "strict", "f1"}: for intent/strict the pass counts of A and B, the
    gained and lost item ids and McNemar's p; for f1 the mean of A and B, delta = B − A, its
    paired-bootstrap 95% interval and p.
    """
    b_by_id = {b["id"]: b for b in b_items if _usable(b)}
    pairs = [(a, b_by_id[a["id"]]) for a in a_items if _usable(a) and a["id"] in b_by_id]
    f1_a = [float(a["f1"]) for a, _ in pairs]
    f1_b = [float(b["f1"]) for _, b in pairs]
    delta, (lo, hi), p = paired_bootstrap(f1_a, f1_b)
    n = len(pairs)
    return {
        "n": n,
        "intent": _flips(pairs, "intent_match"),
        "strict": _flips(pairs, "result_match"),
        "f1": {
            "a": sum(f1_a) / n if n else 0.0,
            "b": sum(f1_b) / n if n else 0.0,
            "delta": delta,
            "ci": (lo, hi),
            "p": p,
        },
    }


def render(out: dict[str, Any], name_a: str, name_b: str) -> str:
    """A Markdown summary of ``compare``'s result."""
    n = out["n"]
    lines = [
        f"# Paired comparison — A = `{name_a}` · B = `{name_b}`",
        "",
        f"Paired items: {n} (scored in both runs; shown-in-prompt and broken-gold items left out).",
        "",
        "| Metric | A | B | B − A | 95% interval (paired bootstrap) | p |",
        "|---|---|---|---|---|---|",
        f"| Macro F1 QALD (headline) | {out['f1']['a']:.3f} | {out['f1']['b']:.3f} | "
        f"{out['f1']['delta']:+.3f} | {out['f1']['ci'][0]:+.3f} – {out['f1']['ci'][1]:+.3f} | "
        f"{out['f1']['p']:.3f} |",
        "",
        "| Metric | A | B | Gains | Losses | Exact McNemar p |",
        "|---|---|---|---|---|---|",
    ]
    for label, key in (("Intent-based match", "intent"), ("Strict execution match", "strict")):
        s = out[key]
        lines.append(
            f"| {label} | {s['a']}/{n} | {s['b']}/{n} | {len(s['gains'])} | "
            f"{len(s['losses'])} | {s['p']:.3f} |"
        )
    lines.append("")
    for label, key in (("Intent", "intent"), ("Strict", "strict")):
        s = out[key]
        lines.append(
            f"- {label} gains: {', '.join(s['gains']) or 'none'} · "
            f"losses: {', '.join(s['losses']) or 'none'}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Paired comparison of two eval runs (JSON).")
    parser.add_argument("a", type=Path, help="first run's .json sidecar (the baseline)")
    parser.add_argument("b", type=Path, help="second run's .json sidecar")
    parser.add_argument("--output", type=Path, default=None, help="write Markdown here too")
    args = parser.parse_args()
    a = json.loads(args.a.read_text(encoding="utf-8"))
    b = json.loads(args.b.read_text(encoding="utf-8"))
    text = render(compare(a["items"], b["items"]), args.a.name, args.b.name)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    # A Windows console may use a legacy code page (cp1253 here) that has no "−" (U+2212):
    # print UTF-8 like backend/dev.ps1 does, instead of crashing after the work is done.
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    print(text)


if __name__ == "__main__":
    main()
