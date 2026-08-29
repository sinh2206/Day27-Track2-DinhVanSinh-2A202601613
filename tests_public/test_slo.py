import pytest
from student_api import multiwindow_burn, slo_status


def test_burn_rate_math():
    result = slo_status(0.995, bad_events=2, total_events=100)
    assert result["allowed_bad_rate"] == pytest.approx(0.005)
    assert result["actual_bad_rate"] == pytest.approx(0.02)
    assert result["burn_rate"] == pytest.approx(4.0)
    assert result["breached"] is True


def test_zero_events_is_safe():
    result = slo_status(0.99, bad_events=0, total_events=0)
    assert result["burn_rate"] == 0
    assert result["breached"] is False


def test_sustained_fast_burn_triggers_page():
    # Both 1h (short) and 6h (long) windows exceed critical 14.4x burn rate
    result = multiwindow_burn(short_window_burn=15.0, long_window_burn=14.8)
    assert result["page"] is True
    assert result["severity"] == "critical"


def test_transient_spike_does_not_page():
    # Short window spiked, but long window remains low -> no paging, avoid alert fatigue
    result = multiwindow_burn(short_window_burn=16.0, long_window_burn=2.0)
    assert result["page"] is False
    assert result["severity"] == "warning"


def test_multiwindow_burn_positional_and_6h_window():
    from observability.slo import evaluate_multiwindow_burn

    # Test positional call with 14.4x short and 6.0x long (6h Google SRE window)
    res_pos = evaluate_multiwindow_burn(14.4, 6.0)
    assert res_pos["page"] is True
    assert res_pos["severity"] == "critical"

    # Test slow burn warning (1.5x, 1.2x) -> no page, warning
    res_slow = evaluate_multiwindow_burn(1.5, 1.2)
    assert res_slow["page"] is False
    assert res_slow["severity"] == "warning"


