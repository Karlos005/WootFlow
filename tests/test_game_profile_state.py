import server
from core.game_profiles import GameProfile


def fresh_state():
    s = server.AppState()
    s.mode, s.current_effect_name = "effect", "breathing"
    s.brightness, s.speed = 0.8, 1.0
    s.color1, s.color2 = (1, 2, 3), (4, 5, 6)
    return s


def profile(**kw):
    return GameProfile.from_dict({"name": "Jogo", "processes": ["jogo.exe"], "effect": "rainbow_wave", **kw})


def test_game_profile_applies_and_restores_user_settings():
    s = fresh_state()
    effect = next(e for e in server.EFFECT_REGISTRY if e != "breathing")
    s._on_game_change(profile(effect=effect, brightness=0.3, color1=[9, 9, 9]))
    assert s.current_effect_name == effect and s.active_game_id
    assert s.brightness == 0.3 and s.color1 == (9, 9, 9) and s.speed == 1.0
    assert s._game_restore["effect"] == "breathing"
    s._on_game_change(None)
    assert s.current_effect_name == "breathing" and s.active_game_id is None
    assert s.brightness == 0.8 and s.color1 == (1, 2, 3) and s._game_restore is None


def test_second_profile_keeps_original_snapshot():
    s = fresh_state()
    effects = [e for e in server.EFFECT_REGISTRY if e != "breathing"][:2]
    s._on_game_change(profile(effect=effects[0], brightness=0.1))
    s._on_game_change(profile(effect=effects[1], brightness=0.2))
    assert s._game_restore["brightness"] == 0.8
    s._on_game_change(None)
    assert s.brightness == 0.8


def test_leds_off_are_not_overridden_by_a_game():
    s = fresh_state()
    s.mode = "off"
    s._on_game_change(profile())
    assert s.mode == "off" and s._game_restore is None


def test_unknown_effect_falls_back_to_breathing():
    s = fresh_state()
    s._on_game_change(profile(effect="does_not_exist"))
    assert s.current_effect_name == "breathing"
    s._on_game_change(None)


def test_save_settings_stores_user_values_while_game_active(monkeypatch=None):
    s = fresh_state()
    saved = {}
    original = server._save_settings
    server._save_settings = saved.update
    try:
        effect = next(e for e in server.EFFECT_REGISTRY if e != "breathing")
        s._on_game_change(profile(effect=effect, brightness=0.3))
        s.save_settings()
    finally:
        server._save_settings = original
    assert saved["brightness"] == 0.8 and saved["effect"] == "breathing"
    assert "game_profiles" in saved


def test_hud_profile_starts_and_stops_the_screen_tracker():
    s = fresh_state()
    hud = {"monitor": 0, "meters": [{"id": "hp", "region": [0.1, 0.9, 0.2, 0.03], "color": [255, 255, 255]}]}
    try:
        s._on_game_change(profile(effect="hud_meters", hud=hud))
        assert s.current_effect_name == "hud_meters"
        assert [m.id for m in server.hud_tracker.meters()] == ["hp"]
        s._on_game_change(None)
        assert server.hud_tracker.meters() == []
        assert s.current_effect_name == "breathing"
    finally:
        server.hud_tracker.stop()
        server.hud_tracker.configure(None)
