import core.effects_engine as eng
from core.devices import default_profile, profile_from_device_info


def _info(**kw):
    base = {"model": "Wooting 60HE", "device_type": "Keyboard 60%", "layout": "ISO",
            "max_rows": 6, "max_columns": 21}
    base.update(kw)
    return base


def teardown_function(_):
    eng.apply_profile(default_profile())


def test_no_device_falls_back_to_60he():
    p = profile_from_device_info(None)
    assert p.key == "60" and p.measured and p.band_count == 14


def test_60_percent_detected_from_device_type():
    p = profile_from_device_info(_info(model="Wooting Two HE", device_type="Keyboard 60%"))
    assert p.key == "60" and p.key_count == 66


def test_full_size_uses_full_grid_and_is_marked_approximate():
    p = profile_from_device_info(_info(model="Wooting Two HE", device_type="Keyboard Full"))
    assert p.key == "full" and not p.measured
    assert p.key_count == 6 * 21 and p.band_count == 21


def test_apply_profile_updates_shared_structures_in_place():
    keys_ref, eq_ref = eng.PHYSICAL_KEYS_60HE, eng.EQ_COLUMNS
    eng.apply_profile(profile_from_device_info(_info(device_type="Keyboard Full", model="X")))
    assert eng.PHYSICAL_KEYS_60HE is keys_ref and eng.EQ_COLUMNS is eq_ref
    assert eng.LAYOUT_COLS == 21 and len(eng.ALL_KEYS) == 6 * 21
    assert sorted(eng.EQ_COLUMNS) == list(range(21))


def test_equalizer_bands_follow_layout_width():
    eng.apply_profile(profile_from_device_info(_info(device_type="Keyboard Full", model="X")))
    eq = eng.EqualizerEffect()
    eq.set_bands([0.0, 1.0] * 7)
    assert len(eq._bands) == 21
