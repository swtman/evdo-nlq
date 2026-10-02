"""Uncertainty and paired tests for eval reports (ADR-038) — plain ``math``/``random``.

WHY
---
The eval sets are small (20 examples, 32 title items), so a rate alone hides how much it could
move by chance: 16/32 is anywhere between about 34% and 66% (Wilson 95%). And two prompt
versions answer the SAME items, so a comparison must be PAIRED — only the items that flipped
carry information about the difference.

- ``wilson``         95% interval for a pass rate (better than ±1.96·SE at small n and near
                     0% / 100%; never leaves [0, 1]).
- ``bootstrap_ci``   95% percentile interval for a mean of per-item scores (macro F1).
- ``mcnemar_exact``  two-sided exact McNemar test on the flips between two runs: under "no
                     difference" a flip is a gain or a loss with probability ½ (Dietterich 1998).
- ``paired_bootstrap`` difference of two macro F1s over the same items, with its interval and
                     p-value (Berg-Kirkpatrick et al. 2012; Dror et al. 2018 as the guide).

Every resampling function takes a ``seed`` so a report is reproducible.
"""

from __future__ import annotations

import math
import random

_Z95 = 1.959963984540054  # standard normal quantile for a two-sided 95% interval


def wilson(k: int, n: int, z: float = _Z95) -> tuple[float, float]:
    """Wilson score interval for ``k`` passes out of ``n`` items; (0, 1) when n = 0."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _percentiles(samples: list[float], alpha: float) -> tuple[float, float]:
    """The alpha/2 and 1 − alpha/2 percentiles of ``samples`` (nearest rank)."""
    samples = sorted(samples)
    lo = samples[int(math.floor(alpha / 2 * (len(samples) - 1)))]
    hi = samples[int(math.ceil((1 - alpha / 2) * (len(samples) - 1)))]
    return (lo, hi)


def bootstrap_ci(
    values: list[float], *, resamples: int = 10_000, seed: int = 0, alpha: float = 0.05
) -> tuple[float, float]:
    """Percentile bootstrap interval for the mean of ``values`` (items resampled with
    replacement); (0, 0) for no values."""
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(values)
    means = [_mean([values[rng.randrange(n)] for _ in range(n)]) for _ in range(resamples)]
    return _percentiles(means, alpha)


def mcnemar_exact(gains: int, losses: int) -> float:
    """Two-sided exact McNemar p-value for ``gains`` / ``losses`` flips between two runs.

    Only the discordant items count. Under the null each is a gain with probability ½, so the
    p-value is twice the binomial tail of the smaller count, capped at 1. Example (the todo's):
    v8 → v9 titles, 5 gains / 2 losses → 2 · 29/128 ≈ 0.45 — not significant.
    """
    n = gains + losses
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(gains, losses) + 1)) / 2**n
    return min(1.0, 2 * tail)


def paired_bootstrap(
    a: list[float],
    b: list[float],
    *,
    resamples: int = 10_000,
    seed: int = 0,
    alpha: float = 0.05,
) -> tuple[float, tuple[float, float], float]:
    """Paired bootstrap for mean(b) − mean(a) over the same items.

    Returns ``(delta, (lo, hi), p)``. Items are resampled in PAIRS. Berg-Kirkpatrick et al.
    (EMNLP-CoNLL 2012, Fig. 1 p. 996 — read) give a ONE-sided test: count the resamples with
    delta* > 2·delta, p ≈ count / b (the resampled gains are centred on delta, not on 0, hence
    the 2·delta). Here the test is TWO-sided — we do not know in advance which version is
    better — so both tails count: ``p = share of |delta* − delta| ≥ |delta|``, about twice
    their one-sided value. delta = 0 gives p = 1. Their b = 10^6; ours 10^4 by default.
    """
    if len(a) != len(b):
        raise ValueError(f"paired samples differ in length: {len(a)} vs {len(b)}")
    if not a:
        return (0.0, (0.0, 0.0), 1.0)
    diffs = [y - x for x, y in zip(a, b, strict=True)]
    delta = _mean(diffs)
    rng = random.Random(seed)
    n = len(diffs)
    samples = [_mean([diffs[rng.randrange(n)] for _ in range(n)]) for _ in range(resamples)]
    if delta == 0:
        return (0.0, _percentiles(samples, alpha), 1.0)
    extreme = sum(abs(s - delta) >= abs(delta) for s in samples)
    return (delta, _percentiles(samples, alpha), extreme / resamples)
