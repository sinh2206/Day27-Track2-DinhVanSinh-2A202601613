from student_api import detect_distribution


def test_extreme_mean_shift_detected():
    baseline = [9, 10, 11, 10, 10]
    current = [190, 200, 210, 205]
    assert detect_distribution(current, baseline)["is_anomaly"] is True


def test_identical_distribution_not_anomaly():
    baseline = [10.0, 12.0, 11.0, 9.0, 10.5, 11.5, 10.0, 12.0]
    current = [10.2, 11.8, 10.9, 9.5, 10.6, 11.2, 10.1, 11.9]
    res = detect_distribution(current, baseline)
    assert res["is_anomaly"] is False

