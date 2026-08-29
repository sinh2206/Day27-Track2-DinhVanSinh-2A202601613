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
    *,
    short_window_burn: float,
    long_window_burn: float,
    policy: str = "google_sre",
    short_threshold: float = 14.4,
    long_threshold: float = 14.4,
) -> dict[str, Any]:
    """Multi-window multi-burn-rate alerting policy based on Google SRE guidelines.

    Principles:
    - Fast burn / Paging (P1): Triggered ONLY when BOTH short window (fast detection)
      and long window (sustained burn) exceed critical thresholds.
    - Transient spike: Short window exceeds threshold, but long window does not -> DO NOT page.
    - Slow/Medium burn: Both exceed medium thresholds -> Ticket/Warning.
    - Healthy: Normal operations within budget.
    """
    # 1. Critical Page: 14.4x burn rate over 1h and 6h windows (2% error budget consumed in 1h)
    if short_window_burn >= short_threshold and long_window_burn >= long_threshold:
        return {
            "page": True,
            "severity": "critical",
            "reason": (
                f"sustained_fast_burn_paging: short_burn={short_window_burn:.2f}>={short_threshold}, "
                f"long_burn={long_window_burn:.2f}>={long_threshold}"
            ),
            "short_window_burn": short_window_burn,
            "long_window_burn": long_window_burn,
            "policy": policy,
        }

    # 2. Medium Burn: 6.0x burn rate over short and long windows (5% budget in 6h)
    if short_window_burn >= 6.0 and long_window_burn >= 6.0:
        return {
            "page": True,
            "severity": "high",
            "reason": (
                f"sustained_medium_burn_paging: short_burn={short_window_burn:.2f}>=6.0, "
                f"long_burn={long_window_burn:.2f}>=6.0"
            ),
            "short_window_burn": short_window_burn,
            "long_window_burn": long_window_burn,
            "policy": policy,
        }

    # 3. Transient Spike: Short window spiked, but long window is normal (avoid alert fatigue)
    if short_window_burn >= short_threshold and long_window_burn < long_threshold:
        return {
            "page": False,
            "severity": "warning",
            "reason": (
                f"transient_spike_no_page: short_burn={short_window_burn:.2f}>={short_threshold} "
                f"but long_burn={long_window_burn:.2f}<{long_threshold}"
            ),
            "short_window_burn": short_window_burn,
            "long_window_burn": long_window_burn,
            "policy": policy,
        }

    # 4. Healthy / within budget
    return {
        "page": False,
        "severity": "info",
        "reason": f"budget_healthy: short_burn={short_window_burn:.2f}, long_burn={long_window_burn:.2f}",
        "short_window_burn": short_window_burn,
        "long_window_burn": long_window_burn,
        "policy": policy,
    }

