from student_api import detect_metric


def test_large_volume_drop_is_anomaly():
    history = [1000, 1010, 995, 1008, 1004, 1012, 998]
    result = detect_metric(300, history, method="zscore")
    assert result["is_anomaly"] is True


def test_stable_value_is_not_anomaly():
    history = [1000, 1010, 995, 1008, 1004, 1012, 998]
    result = detect_metric(1002, history, method="zscore")
    assert result["is_anomaly"] is False


def test_mad_handles_zero_mad_gracefully():
    # History with identical values has MAD = 0
    history = [100.0, 100.0, 100.0, 100.0, 100.0]
    res_normal = detect_metric(100.0, history, method="mad")
    assert res_normal["is_anomaly"] is False

    res_outlier = detect_metric(150.0, history, method="mad")
    assert res_outlier["is_anomaly"] is True


def test_auto_uses_seasonality_context():
    # Overall daily history fluctuates, but Saturday history is consistently lower
    general_history = [1000, 1050, 980, 1020, 500, 1010, 1005]
    saturday_history = [500, 510, 495, 505]

    # Without context, 500 might look like an anomaly against ~1000 average
    # With same_segment_history context for Saturday, 505 is normal
    res = detect_metric(
        505,
        general_history,
        method="auto",
        context={"metric_name": "row_count", "day_of_week": 5, "same_segment_history": saturday_history},
    )
    assert res["is_anomaly"] is False
    assert "seasonal_mad" in res["method"]


def test_auto_detects_true_volume_drop():
    history = [600, 595, 605, 598, 602, 601, 599]
    res = detect_metric(150, history, method="auto")
    assert res["is_anomaly"] is True

