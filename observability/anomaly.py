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
import pandas as pd


def zscore_detector(
    current: float,
    history: Iterable[float],
    threshold: float = 3.0,
) -> dict[str, Any]:
    """Standard Z-score anomaly detector."""
    if isinstance(history, (pd.Series, pd.DataFrame)):
        values = history.dropna().values.astype(float)
    else:
        values = np.asarray(list(history), dtype=float)
        values = values[~np.isnan(values)]

    if values.size < 2:
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
    if isinstance(history, (pd.Series, pd.DataFrame)):
        values = history.dropna().values.astype(float)
    else:
        values = np.asarray(list(history), dtype=float)
        values = values[~np.isnan(values)]

    if values.size < 2:
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


def _extract_context_segment(
    history: Iterable[float],
    context: dict[str, Any] | None,
) -> tuple[np.ndarray, str]:
    """Extract context-aware subsegment (e.g. same day-of-week) from history."""
    ctx = context or {}
    dow = ctx.get("day_of_week")

    # 1. Explicit same_segment_history passed in context
    if "same_segment_history" in ctx and ctx["same_segment_history"] is not None:
        seg = np.asarray(list(ctx["same_segment_history"]), dtype=float)
        seg = seg[~np.isnan(seg)]
        if seg.size >= 2:
            return seg, "auto:seasonal_mad"

    # 2. History passed as pandas DataFrame with day_of_week column
    if isinstance(history, pd.DataFrame):
        metric = ctx.get("metric_name", "row_count")
        col = metric if metric in history.columns else history.select_dtypes(include=[np.number]).columns[-1]
        if dow is not None and "day_of_week" in history.columns:
            seg = history.loc[history["day_of_week"] == dow, col].dropna().values.astype(float)
            if seg.size >= 2:
                return seg, "auto:seasonal_mad"
        return history[col].dropna().values.astype(float), "auto:mad"

    # 3. History passed as pandas Series with datetime index
    if isinstance(history, pd.Series):
        if dow is not None and hasattr(history.index, "dayofweek"):
            seg = history[history.index.dayofweek == dow].dropna().values.astype(float)
            if seg.size >= 2:
                return seg, "auto:seasonal_mad"
        return history.dropna().values.astype(float), "auto:mad"

    # 4. History passed as flat list or array of daily sequential values
    vals = np.asarray(list(history), dtype=float)
    vals = vals[~np.isnan(vals)]

    if dow is not None and vals.size >= 7:
        # Extract matching weekday stride (e.g. index % 7 == dow)
        stride_candidates = [
            vals[dow::7],
            vals[- (7 - dow)::7] if dow < 7 else vals,
            vals[(dow - (vals.size % 7)) % 7::7],
        ]
        for c in stride_candidates:
            if c.size >= 2:
                return c, "auto:seasonal_mad"

    return vals, "auto:mad"


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
        - `same_segment_history` / `day_of_week`: compares against same weekday.
        - `known_event`: suppresses false alarms for expected promotional spikes.
        - Defaults to robust MAD detector to avoid outlier masking.
    """
    if method == "zscore":
        return zscore_detector(current, history, threshold=threshold)

    if method == "mad":
        return mad_detector(current, history, threshold=threshold)

    if method == "auto":
        ctx = context or {}
        eff_history, method_name = _extract_context_segment(history, ctx)

        # Compute MAD score on the effective history
        result = mad_detector(current, eff_history, threshold=threshold)
        
        # Fallback to general history if segment was too small
        if result["reason"] == "insufficient_history":
            gen_vals = np.asarray(list(history), dtype=float)
            gen_vals = gen_vals[~np.isnan(gen_vals)]
            if gen_vals.size >= 3:
                result = mad_detector(current, gen_vals, threshold=threshold)
                method_name = "auto:mad"

        result["method"] = method_name

        # Context-aware event handling (e.g. promo/flash sale where spike is expected)
        if ctx.get("known_event"):
            median = float(np.median(eff_history)) if eff_history.size > 0 else 0.0
            if float(current) >= median:
                # Promotional increase is expected and legitimate
                result["is_anomaly"] = False
                result["reason"] += " [known_event_spike_accepted]"
            else:
                # A drop during a promo is still an anomaly
                result["reason"] += " [known_event_drop]"

        if ctx:
            ctx_summary = ", ".join(f"{k}={v}" for k, v in ctx.items() if k != "same_segment_history")
            if ctx_summary and "[context:" not in result["reason"]:
                result["reason"] += f" [context: {ctx_summary}]"

        return result

    raise ValueError(f"Unsupported method: {method}")


