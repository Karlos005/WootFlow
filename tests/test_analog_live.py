from core.analog_live import HID_TO_KEY_IDS, depths_to_key_ids


def test_maps_letters_and_ignores_released_keys():
    out = depths_to_key_ids([4, 22, 20], [0.5, 0.0, 1.4])
    assert out == {"3-1": 0.5, "2-1": 1.0}


def test_space_lights_all_five_leds_and_unknown_codes_are_skipped():
    out = depths_to_key_ids([44, 999], [0.8, 0.9])
    assert sorted(out) == ["5-4", "5-5", "5-6", "5-7", "5-8"]


def test_no_key_id_is_shared_between_hid_codes():
    ids = [k for keys in HID_TO_KEY_IDS.values() for k in keys]
    assert len(ids) == len(set(ids))
