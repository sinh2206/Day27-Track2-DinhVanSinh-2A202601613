from __future__ import annotations

from typing import Any


def calculate_slo(target: float, bad_events: int, total_events: int) -> dict[str, Any]:
    if not 0 < target < 1:
        raise ValueError("target must be between 0 and 1 (exclusive)")
    if bad_events < 0 or total_events < 0 or bad_events > total_events:
        raise ValueError("invalid event counts")
    allowed_bad_rate = 1.0 - target
    if total_events == 0:
        return {
            "target": target,
            "actual_bad_rate": 0.0,
            "allowed_bad_rate": allowed_bad_rate,
            "burn_rate": 0.0,
            "remaining_error_budget_fraction": 1.0,
            "breached": False,
        }
    actual_bad_rate = bad_events / total_events
    burn_rate = actual_bad_rate / allowed_bad_rate
    consumed_fraction = min(1.0, actual_bad_rate / allowed_bad_rate)
    return {
        "target": target,
        "actual_bad_rate": actual_bad_rate,
        "allowed_bad_rate": allowed_bad_rate,
        "burn_rate": burn_rate,
        "remaining_error_budget_fraction": max(0.0, 1.0 - consumed_fraction),
        "breached": bool(actual_bad_rate > allowed_bad_rate),
    }


def evaluate_multiwindow_burn(
    short_window_burn: float = 0.0,
    long_window_burn: float = 0.0,
    *,
    policy: str = "google_sre",
    short_threshold: float = 14.4,
    long_threshold: float = 14.4,
    **kwargs: Any,
) -> dict[str, Any]:
    """Multi-window multi-burn-rate alerting policy based on Google SRE guidelines.

    Supports both positional and keyword invocations.

    Principles:
    - Fast burn / Paging (P1): Triggered when BOTH short window (fast detection)
      and long window (sustained burn) exceed critical thresholds:
      * 1-hour fast burn: short >= 14.4 and long >= 14.4 (2% budget in 1h)
      * 6-hour medium burn: short >= 6.0 and long >= 6.0 (5% budget in 6h)
      * Custom thresholds: short >= short_threshold and long >= long_threshold
    - Transient spike: Short window exceeds threshold, but long window does not -> DO NOT page (avoid alert fatigue).
    - Slow burn: Both >= 1.0 -> Non-paging ticket/warning.
    - Healthy: Normal operations within budget.
    """
    s_burn = float(short_window_burn)
    l_burn = float(long_window_burn)

    # 1. Critical Page: Sustained fast burn over both short and long windows
    if (
        (s_burn >= short_threshold and l_burn >= long_threshold)
        or (s_burn >= 14.4 and l_burn >= 6.0)
        or (s_burn >= 6.0 and l_burn >= 6.0)
    ):
        return {
            "page": True,
            "severity": "critical",
            "reason": (
                f"sustained_fast_burn_paging: short_burn={s_burn:.2f}>={short_threshold}, "
                f"long_burn={l_burn:.2f}>={long_threshold}"
            ),
            "short_window_burn": s_burn,
            "long_window_burn": l_burn,
            "policy": policy,
        }

    # 2. Transient Spike: Short window spiked, but long window is normal (avoid alert fatigue)
    if (s_burn >= short_threshold or s_burn >= 6.0) and l_burn < 6.0:
        return {
            "page": False,
            "severity": "warning",
            "reason": (
                f"transient_spike_no_page: short_burn={s_burn:.2f} spiked "
                f"but long_burn={l_burn:.2f} is below sustained threshold"
            ),
            "short_window_burn": s_burn,
            "long_window_burn": l_burn,
            "policy": policy,
        }

    # 3. Slow Burn Warning: e.g. 3-day 1.0x burn (10% budget in 3 days)
    if s_burn >= 1.0 and l_burn >= 1.0:
        return {
            "page": False,
            "severity": "warning",
            "reason": f"slow_burn_warning: short_burn={s_burn:.2f}, long_burn={l_burn:.2f}",
            "short_window_burn": s_burn,
            "long_window_burn": l_burn,
            "policy": policy,
        }

    # 4. Healthy / within budget
    return {
        "page": False,
        "severity": "info",
        "reason": f"budget_healthy: short_burn={s_burn:.2f}, long_burn={l_burn:.2f}",
        "short_window_burn": s_burn,
        "long_window_burn": l_burn,
        "policy": policy,
    }


