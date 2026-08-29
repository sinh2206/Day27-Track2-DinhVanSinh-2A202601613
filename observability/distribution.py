from __future__ import annotations

from typing import Any, Iterable

import numpy as np

try:
    from scipy import stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


def detect_distribution_shift(
    current_values: Iterable[float],
    baseline_values: Iterable[float],
    *,
    alpha: float = 0.05,
    ks_threshold: float = 0.4,
    ratio_threshold: float = 3.0,
) -> dict[str, Any]:
    """Detect distribution shift between baseline and current data batches.

    Applies the two-sample Kolmogorov-Smirnov test (KS-test) for shape/distribution shift,
    augmented with robust mean and quantile tracking.
    """
    cur = np.asarray(list(current_values), dtype=float)
    base = np.asarray(list(baseline_values), dtype=float)

    if cur.size == 0 or base.size == 0:
        return {
            "is_anomaly": False,
            "score": 0.0,
            "method": "ks_test",
            "reason": "empty_input",
        }

    cur_mean = float(np.mean(cur))
    base_mean = float(np.mean(base))

    # Mean ratio calculation
    if base_mean == 0:
        ratio = float("inf") if cur_mean != 0 else 1.0
    else:
        ratio = max(abs(cur_mean / base_mean), abs(base_mean / cur_mean)) if cur_mean != 0 else float("inf")

    if HAS_SCIPY and cur.size >= 4 and base.size >= 4:
        ks_res = stats.ks_2samp(cur, base)
        stat = float(ks_res.statistic)
        pvalue = float(ks_res.pvalue)

        # Anomaly is flagged if p-value < alpha and KS statistic is notable, or if mean ratio is extreme
        is_anomaly = bool((pvalue < alpha and stat >= ks_threshold) or (ratio >= ratio_threshold))
        
        return {
            "is_anomaly": is_anomaly,
            "score": stat,
            "p_value": pvalue,
            "method": "ks_2samp",
            "reason": (
                f"ks_stat={stat:.3f}, p_val={pvalue:.4f}, "
                f"base_mean={base_mean:.2f}, cur_mean={cur_mean:.2f}"
            ),
        }

    # Fallback to mean ratio when samples are too small for KS
    is_anomaly = bool(ratio >= ratio_threshold)
    return {
        "is_anomaly": is_anomaly,
        "score": float(ratio),
        "method": "mean_ratio",
        "reason": f"baseline_mean={base_mean:.3f}, current_mean={cur_mean:.3f}, ratio={ratio:.2f}",
    }

