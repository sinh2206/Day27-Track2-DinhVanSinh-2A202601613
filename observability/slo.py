from __future__ import annotations

from typing import Any


def calculate_slo(
    target: float,
    bad_events: int | float,
    total_events: int | float,
    **kwargs: Any,
) -> dict[str, Any]:
    # Normalize percentage target (e.g. 99.5 -> 0.995)
    t = float(target)
    if 1.0 < t <= 100.0:
        t = t / 100.0

    if not 0 < t < 1:
        raise ValueError("target must be between 0 and 1 (exclusive)")

    bad = int(bad_events)
    total = int(total_events)

    if bad < 0 or total < 0 or bad > total:
        raise ValueError("invalid event counts")

    allowed_bad_rate = 1.0 - t
    if total == 0:
        return {
            "target": t,
            "actual_bad_rate": 0.0,
            "allowed_bad_rate": allowed_bad_rate,
            "burn_rate": 0.0,
            "remaining_error_budget_fraction": 1.0,
            "breached": False,
        }

    actual_bad_rate = bad / total
    burn_rate = actual_bad_rate / allowed_bad_rate
    consumed_fraction = min(1.0, actual_bad_rate / allowed_bad_rate)
    return {
        "target": t,
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
      and long window (sustained burn) exceed critical thresholds (default: >= 14.4x).
    - Transient spike: Short window exceeds threshold, but long window does not -> DO NOT page.
    - Slow burn: Both >= 1.0 -> Non-paging ticket/warning.
    - Healthy: Normal operations within budget.
    """
    s_burn = float(short_window_burn)
    l_burn = float(long_window_burn)

    # 1. Critical Page: Sustained fast burn over both short and long windows
    if s_burn >= short_threshold and l_burn >= long_threshold:
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
    if s_burn >= short_threshold and l_burn < long_threshold:
        return {
            "page": False,
            "severity": "warning",
            "reason": (
                f"transient_spike_no_page: short_burn={s_burn:.2f} spiked "
                f"but long_burn={l_burn:.2f} is below sustained threshold {long_threshold}"
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



