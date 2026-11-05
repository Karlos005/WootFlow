from core.rgb_sleep import DIM_LEVEL, normalize_minutes, sleep_factor


def test_factor_follows_idle_time():
    assert sleep_factor(0, 5, 10) == 1.0
    assert sleep_factor(5 * 60, 5, 10) == DIM_LEVEL
    assert sleep_factor(10 * 60, 5, 10) == 0.0


def test_never_disables_each_stage():
    assert sleep_factor(99999, None, None) == 1.0
    assert sleep_factor(99999, 5, None) == DIM_LEVEL
    assert sleep_factor(99999, None, 10) == 0.0


def test_normalize_minutes_accepts_only_known_steps():
    assert normalize_minutes(10) == 10
    assert normalize_minutes(7) is None
    assert normalize_minutes(None) is None
    assert normalize_minutes(True) is None
    assert normalize_minutes("5") is None
