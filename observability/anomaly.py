"""Statistical anomaly detection for metric streams and daily aggregates.

Provides:
- `zscore_detector`: Standard Z-score baseline (sensitive to existing outliers).
- `mad_detector`: Median Absolute Deviation (MAD) robust baseline with zero-MAD edge case handling.
- `detect_anomaly`: Context-aware automatic detector handling seasonality (e.g., same-weekday history),
  known events (e.g., promotional campaigns), and dynamic thresholding.
"""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def zscore_detector(
    current: float,
    history: Iterable[float],
    threshold: float = 3.0,
) -> dict[str, Any]:
    """Standard Z-score anomaly detector."""
    values = np.asarray(list(history), dtype=float)
    if values.size < 3:
        return {
            "is_anomaly": False,
            "score": 0.0,
            "method": "zscore",
            "reason": "insufficient_history",
        }

    mean = float(np.mean(values))
    std = float(np.std(values))

    if std == 0:
        score = float("inf") if float(current) != mean else 0.0
    else:
        score = abs(float(current) - mean) / std

    return {
        "is_anomaly": bool(score > threshold),
        "score": float(score),
        "method": "zscore",
        "reason": f"mean={mean:.3f}, std={std:.3f}, threshold={threshold}",
    }


def mad_detector(
    current: float,
    history: Iterable[float],
    threshold: float = 3.5,
) -> dict[str, Any]:
    """Median Absolute Deviation (MAD) robust anomaly detector.

    Uses Boris Iglewicz and David Hoaglin's modified Z-score formula:
        M_i = 0.6745 * |x_i - median| / MAD
    Handles zero-MAD edge cases cleanly when history has identical values.
    """
    values = np.asarray(list(history), dtype=float)
    if values.size < 3:
        return {
            "is_anomaly": False,
            "score": 0.0,
            "method": "mad",
            "reason": "insufficient_history",
        }

    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))

    if mad == 0:
        # Zero-MAD edge case: if current equals median, perfectly normal (score=0.0).
        # If current differs from uniform baseline, it is an anomaly (score=inf).
        diff = abs(float(current) - median)
        if diff < 1e-9:
            score = 0.0
        else:
            score = float("inf")
        return {
            "is_anomaly": bool(score > threshold),
            "score": float(score),
            "method": "mad",
            "reason": f"median={median:.3f}, mad=0.0 (uniform_history), diff={diff:.3f}",
        }

    modified_z = 0.6745 * abs(float(current) - median) / mad
    return {
        "is_anomaly": bool(modified_z > threshold),
        "score": float(modified_z),
        "method": "mad",
        "reason": f"median={median:.3f}, mad={mad:.3f}, threshold={threshold}",
    }


def detect_anomaly(
    current: float,
    history: Iterable[float],
    *,
    method: str = "auto",
    threshold: float = 3.0,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stable API for anomaly detection.

    Modes:
    - `zscore`: Standard z-score.
    - `mad`: Robust Median Absolute Deviation.
    - `auto`: Context-aware detector that evaluates:
        - `same_segment_history`: compares against same day-of-week or category.
        - `known_event`: adjusts tolerance during expected anomalies (e.g. flash sales).
        - Defaults to robust MAD detector to avoid mask effects caused by outliers in history.
    """
    if method == "zscore":
        return zscore_detector(current, history, threshold=threshold)

    if method == "mad":
        return mad_detector(current, history, threshold=threshold)

    if method == "auto":
        ctx = context or {}
        segment_history = ctx.get("same_segment_history")
        
        # 1. Seasonality awareness: if same-weekday or segment history is provided with >=3 points, use it
        if segment_history is not None:
            seg_vals = list(segment_history)
            if len(seg_vals) >= 3:
                eff_history = seg_vals
                method_name = "auto:seasonal_mad"
            else:
                eff_history = list(history)
                method_name = "auto:mad"
        else:
            eff_history = list(history)
            method_name = "auto:mad"

        # 2. Known event awareness: widen threshold if event is scheduled
        effective_threshold = threshold
        if ctx.get("known_event"):
            effective_threshold = threshold * 2.0

        result = mad_detector(current, eff_history, threshold=effective_threshold)
        
        # Fallback to Z-score if MAD had insufficient history but general history is longer
        if result["reason"] == "insufficient_history" and len(list(history)) >= 3:
            result = zscore_detector(current, history, threshold=threshold)
            result["method"] = "auto:zscore"
        else:
            result["method"] = method_name

        if ctx:
            ctx_summary = ", ".join(f"{k}={v}" for k, v in ctx.items() if k != "same_segment_history")
            if ctx_summary:
                result["reason"] += f" [context: {ctx_summary}]"

        return result

    raise ValueError(f"Unsupported method: {method}")

