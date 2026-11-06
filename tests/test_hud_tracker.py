import numpy as np

from core.game_profiles import GameProfile
from core.hud_tracker import HudConfig, HudTracker, Meter, measure_fraction


def meter(**kw):
    data = {"id": "hp", "name": "Vida", "region": [0.1, 0.8, 0.2, 0.05], "color": [255, 255, 255], **kw}
    return Meter.from_dict(data)


def bar(width, filled, color=(255, 255, 255), height=10):
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :filled] = color
    return img


def test_fraction_matches_filled_columns():
    m = meter()
    assert measure_fraction(bar(100, 100), m) == 1.0
    assert abs(measure_fraction(bar(100, 40), m) - 0.4) < 0.01
    assert measure_fraction(bar(100, 0), m) == 0.0


def test_color_tolerance_and_other_colors_ignored():
    m = meter(tolerance=30)
    assert abs(measure_fraction(bar(100, 50, color=(250, 250, 255)), m) - 0.5) < 0.01
    assert measure_fraction(bar(100, 50, color=(255, 0, 0)), m) == 0.0


def test_vertical_bar_uses_rows():
    m = meter(orientation="vertical")
    img = np.zeros((100, 10, 3), dtype=np.uint8)
    img[60:] = 255
    assert abs(measure_fraction(img, m) - 0.4) < 0.01


def test_meter_validation():
    assert Meter.from_dict({"region": [0, 0, 0, 0], "color": [1, 2, 3]}) is None
    assert Meter.from_dict({"region": [0.5, 0.5, 0.9, 0.9], "color": [1, 2, 3]}).region[2] == 0.5
    assert Meter.from_dict({"region": [0, 0, 0.1, 0.1]}) is None
    assert Meter.from_dict("x") is None
    assert meter(row=99).row == 5


def test_hud_config_needs_valid_meters_and_round_trips():
    assert HudConfig.from_dict({"meters": [{"region": [0, 0, 0, 0]}]}) is None
    cfg = HudConfig.from_dict({"monitor": 1, "meters": [meter().to_dict()]})
    assert HudConfig.from_dict(cfg.to_dict()) == cfg


def test_tracker_smooths_and_flashes_on_drop():
    tracker = HudTracker()
    tracker.configure(HudConfig(meters=[meter()]))
    tracker.update_from_frames({"hp": 1.0}, 100.0)
    assert tracker.snapshot(100.0)["hp"]["flash"] == 0.0
    tracker.update_from_frames({"hp": 0.4}, 100.1)
    snap = tracker.snapshot(100.1)["hp"]
    assert 0.4 < snap["fraction"] < 1.0 and snap["flash"] > 0.9
    assert tracker.snapshot(101.0)["hp"]["flash"] == 0.0       # o flash desvanece


def test_no_flash_when_disabled_and_unknown_meter_ignored():
    tracker = HudTracker()
    tracker.configure(HudConfig(meters=[meter(flash_on_drop=False)]))
    tracker.update_from_frames({"hp": 1.0, "other": 1.0}, 1.0)
    tracker.update_from_frames({"hp": 0.2}, 1.1)
    assert tracker.snapshot(1.1)["hp"]["flash"] == 0.0
    assert "other" not in tracker.snapshot(1.1)


def test_profile_carries_hud_config():
    p = GameProfile.from_dict({
        "name": "Valorant", "processes": ["valorant-win64-shipping.exe"], "effect": "hud_meters",
        "hud": {"monitor": 0, "meters": [meter().to_dict()]},
    })
    assert p.hud and p.hud.meters[0].id == "hp"
    assert GameProfile.from_dict(p.to_dict()) == p
    assert GameProfile.from_dict({"name": "X", "processes": ["a.exe"]}).hud is None
