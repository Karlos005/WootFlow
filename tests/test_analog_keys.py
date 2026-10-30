from core.analog_keys import AnalogTuning, KeyTuning, RapidTriggerEngine


def run(engine, path):
    return [engine.update(mm) for mm in path]


def test_plain_actuation_point():
    e = RapidTriggerEngine(KeyTuning(actuation_mm=2.0))
    assert run(e, [0.5, 1.9, 2.0, 3.0, 1.9, 0.0]) == [False, False, True, True, False, False]


def test_rapid_trigger_releases_and_repress_without_leaving_travel():
    e = RapidTriggerEngine(KeyTuning(actuation_mm=1.5, rapid_trigger=True, sensitivity_mm=0.4))
    # press at 1.5, dive to 3.0, rise 0.4 -> release, sink 0.4 -> press again
    out = run(e, [1.0, 1.5, 3.0, 2.7, 2.6, 2.9, 3.0])
    assert out == [False, True, True, True, False, False, True]


def test_rapid_trigger_stays_pressed_below_actuation_after_first_press():
    e = RapidTriggerEngine(KeyTuning(actuation_mm=2.0, rapid_trigger=True, sensitivity_mm=0.3))
    assert run(e, [2.0, 1.8, 1.6]) == [True, True, False]  # 0.2 rise holds, 0.4 rise releases


def test_full_release_rearms_requiring_actuation_again():
    e = RapidTriggerEngine(KeyTuning(actuation_mm=2.0, rapid_trigger=True, sensitivity_mm=0.3))
    assert run(e, [2.5, 0.0, 1.0, 2.0]) == [True, False, False, True]


def test_separate_up_and_down_sensitivity():
    e = RapidTriggerEngine(
        KeyTuning(actuation_mm=1.0, rapid_trigger=True, separate_sensitivity=True,
                  upstroke_mm=0.2, downstroke_mm=1.0)
    )
    # releases after 0.2 rise, but needs a full 1.0 mm sink to press again
    assert run(e, [3.0, 2.8, 3.5, 3.9]) == [True, False, False, True]


def test_apply_clamps_and_persists_roundtrip():
    t = AnalogTuning()
    t.apply(["1-1", "1-2"], {"actuationMm": 9, "rapidTrigger": True, "sensitivityMm": 0.0})
    assert t.for_key("1-1").actuation_mm == 4.0
    assert t.for_key("1-2").sensitivity_mm == 0.1
    again = AnalogTuning.from_dict(t.to_dict())
    assert again.for_key("1-1") == t.for_key("1-1")
    assert again.for_key("3-3") == t.default
