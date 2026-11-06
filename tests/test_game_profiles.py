from core.game_profiles import (
    GameProfile, GameProfileStore, GameWatcher, normalize_process, pick_profile,
    running_processes, visible_window_processes,
)


def make(name="CS2", processes=("cs2.exe",), **kw):
    return GameProfile.from_dict({"name": name, "processes": list(processes), **kw})


def test_normalize_process_accepts_paths_and_adds_exe():
    assert normalize_process(r"C:\Games\CS2\Cs2.EXE") == "cs2.exe"
    assert normalize_process("valorant") == "valorant.exe"
    assert normalize_process("  ") is None
    assert normalize_process(5) is None
    assert normalize_process("bad|name.exe") is None


def test_from_dict_rejects_profiles_without_name_or_process():
    assert GameProfile.from_dict({"name": "", "processes": ["a.exe"]}) is None
    assert GameProfile.from_dict({"name": "X", "processes": []}) is None
    assert GameProfile.from_dict("nope") is None


def test_from_dict_clamps_values_and_generates_safe_id():
    p = GameProfile.from_dict({
        "id": "../evil", "name": "X", "processes": ["a.exe", "A.EXE"],
        "brightness": 7, "speed": "x", "color1": [300, -5, 10], "trigger": "weird",
    })
    assert p.id != "../evil" and len(p.id) == 8
    assert p.processes == ["a.exe"]
    assert p.brightness == 1.0 and p.speed is None
    assert p.color1 == (255, 0, 10)
    assert p.trigger == "running"


def test_round_trip_through_store():
    store = GameProfileStore()
    p = make(brightness=0.4, color1=[1, 2, 3])
    store.upsert(p)
    again = GameProfileStore()
    again.load(store.to_list())
    assert again.snapshot() == [p]


def test_pick_profile_running_vs_focused_and_disabled():
    run = make("Run", ["a.exe"])
    focus = make("Focus", ["b.exe"], trigger="focused")
    off = make("Off", ["c.exe"], enabled=False)
    profiles = [run, focus, off]
    assert pick_profile(profiles, {"a.exe"}, None) is run
    assert pick_profile(profiles, {"b.exe"}, None) is None          # focused precisa de foco
    assert pick_profile(profiles, {"b.exe"}, "b.exe") is focus
    assert pick_profile(profiles, {"c.exe"}, "c.exe") is None       # desativado
    assert pick_profile(profiles, {"a.exe", "b.exe"}, "b.exe") is focus  # o foco ganha


def test_store_limits_and_delete():
    store = GameProfileStore()
    p = make()
    assert store.upsert(p)
    assert store.delete(p.id) and not store.delete(p.id)


def test_watcher_fires_on_start_stop_and_edit():
    store = GameProfileStore()
    p = make("Game", ["g.exe"])
    store.upsert(p)
    running = {"set": set()}
    seen = []
    enabled = {"on": True}
    w = GameWatcher(store, seen.append, is_enabled=lambda: enabled["on"],
                    get_running=lambda: running["set"], get_foreground=lambda: None)

    w.tick()
    assert seen == []                       # jogo fechado: nada a fazer
    running["set"] = {"g.exe"}
    w.tick(); w.tick()
    assert seen == [p]                      # só avisa uma vez
    edited = GameProfile.from_dict({**p.to_dict(), "effect": "rain"})
    store.upsert(edited)
    w.tick()
    assert seen == [p, edited]              # edição reaplica
    enabled["on"] = False
    w.tick()
    assert seen[-1] is None                 # desligar o recurso repõe o normal
    assert w.current is None
    enabled["on"] = True
    w.tick()
    assert seen[-1] == edited               # jogo ainda aberto: volta a aplicar
    running["set"] = set()
    w.tick()
    assert seen[-1] is None and w.current is None


def test_windows_detection_runs_and_returns_names():
    names = running_processes()
    assert all(isinstance(n, str) and n == n.lower() for n in names)
    assert isinstance(visible_window_processes(), list)
