"""Perfis de jogo: troca automática de efeito quando um jogo está em execução.

Cada perfil liga um ou mais executáveis a um efeito (e opcionalmente brilho,
velocidade e cores). O `GameWatcher` vigia os processos do Windows e avisa
quando o perfil ativo muda, tal como as "aplicações" do Aurora ou do SignalRGB.
"""
from __future__ import annotations

import ctypes
import re
import sys
import threading
import uuid
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Callable, Iterable

from core.hud_tracker import HudConfig

TRIGGERS = ("running", "focused")
MAX_PROFILES = 64
MAX_PROCESSES_PER_PROFILE = 16

# Processos que aparecem sempre com janela mas nunca são jogos.
_IGNORED_WINDOW_PROCESSES = {
    "explorer.exe", "textinputhost.exe", "applicationframehost.exe",
    "systemsettings.exe", "searchhost.exe", "startmenuexperiencehost.exe",
    "shellexperiencehost.exe", "lockapp.exe", "widgets.exe", "wootflow.exe",
    "python.exe", "pythonw.exe",
}


def normalize_process(name) -> str | None:
    """Reduz um caminho ou nome a `nome.exe` em minúsculas; None se inválido."""
    if not isinstance(name, str):
        return None
    base = re.split(r"[\\/]", name.strip())[-1].strip().lower()
    if not base or len(base) > 80 or re.search(r'[<>:"|?*\x00-\x1f]', base):
        return None
    if "." not in base:
        base += ".exe"
    return base


def _clean_color(value) -> tuple | None:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    try:
        return tuple(max(0, min(255, int(v))) for v in value[:3])
    except (TypeError, ValueError):
        return None


def _clean_float(value, lo: float, hi: float) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return None


@dataclass
class GameProfile:
    id: str
    name: str
    processes: list = field(default_factory=list)
    effect: str = "breathing"
    trigger: str = "running"        # "running": jogo aberto; "focused": jogo em primeiro plano
    enabled: bool = True
    brightness: float | None = None  # None = manter o do utilizador
    speed: float | None = None
    color1: tuple | None = None
    color2: tuple | None = None
    hud: HudConfig | None = None     # medidores lidos do ecrã (usados com o efeito hud_meters)

    @classmethod
    def from_dict(cls, data) -> "GameProfile | None":
        """Valida dados vindos do disco ou do cliente; devolve None se inutilizáveis."""
        if not isinstance(data, dict):
            return None
        name = str(data.get("name", "")).strip()[:60]
        raw_processes = data.get("processes")
        if isinstance(raw_processes, str):
            raw_processes = [raw_processes]
        processes = []
        for item in raw_processes or []:
            proc = normalize_process(item)
            if proc and proc not in processes:
                processes.append(proc)
        processes = processes[:MAX_PROCESSES_PER_PROFILE]
        if not name or not processes:
            return None
        effect = str(data.get("effect") or "breathing").strip()[:60]
        trigger = data.get("trigger") if data.get("trigger") in TRIGGERS else "running"
        raw_id = str(data.get("id") or "").strip()
        profile_id = raw_id if re.fullmatch(r"[a-z0-9_-]{1,32}", raw_id) else uuid.uuid4().hex[:8]
        return cls(
            id=profile_id,
            name=name,
            processes=processes,
            effect=effect,
            trigger=trigger,
            enabled=bool(data.get("enabled", True)),
            brightness=_clean_float(data.get("brightness"), 0.0, 1.0),
            speed=_clean_float(data.get("speed"), 0.1, 5.0),
            color1=_clean_color(data.get("color1")),
            color2=_clean_color(data.get("color2")),
            hud=HudConfig.from_dict(data.get("hud")),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "processes": list(self.processes),
            "effect": self.effect,
            "trigger": self.trigger,
            "enabled": self.enabled,
            "brightness": self.brightness,
            "speed": self.speed,
            "color1": list(self.color1) if self.color1 else None,
            "color2": list(self.color2) if self.color2 else None,
            "hud": self.hud.to_dict() if self.hud else None,
        }


class GameProfileStore:
    """Lista de perfis, protegida por lock porque o watcher lê noutra thread."""

    def __init__(self):
        self._lock = threading.Lock()
        self._profiles: list[GameProfile] = []

    def load(self, items) -> None:
        profiles = []
        seen = set()
        for item in items if isinstance(items, list) else []:
            profile = GameProfile.from_dict(item)
            if profile and profile.id not in seen:
                seen.add(profile.id)
                profiles.append(profile)
        with self._lock:
            self._profiles = profiles[:MAX_PROFILES]

    def snapshot(self) -> list[GameProfile]:
        with self._lock:
            return list(self._profiles)

    def get(self, profile_id: str) -> GameProfile | None:
        return next((p for p in self.snapshot() if p.id == profile_id), None)

    def upsert(self, profile: GameProfile) -> bool:
        with self._lock:
            for i, existing in enumerate(self._profiles):
                if existing.id == profile.id:
                    self._profiles[i] = profile
                    return True
            if len(self._profiles) >= MAX_PROFILES:
                return False
            self._profiles.append(profile)
            return True

    def delete(self, profile_id: str) -> bool:
        with self._lock:
            before = len(self._profiles)
            self._profiles = [p for p in self._profiles if p.id != profile_id]
            return len(self._profiles) != before

    def to_list(self) -> list[dict]:
        return [p.to_dict() for p in self.snapshot()]


def pick_profile(profiles: Iterable[GameProfile], running: set, foreground: str | None) -> GameProfile | None:
    """Escolhe o perfil ativo. O jogo em primeiro plano ganha; senão vale a ordem da lista."""
    matches = []
    for profile in profiles:
        if not profile.enabled:
            continue
        procs = set(profile.processes)
        if profile.trigger == "focused":
            hit = foreground is not None and foreground in procs
        else:
            hit = bool(procs & running)
        if hit:
            matches.append(profile)
    for profile in matches:
        if foreground is not None and foreground in profile.processes:
            return profile
    return matches[0] if matches else None


# ── Deteção de processos (Windows) ──

def _win_api():
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    u32 = ctypes.WinDLL("user32", use_last_error=True)

    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    for fn in (k32.Process32FirstW, k32.Process32NextW):
        fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
        fn.restype = wintypes.BOOL
    u32.GetForegroundWindow.restype = wintypes.HWND
    u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    u32.IsWindowVisible.argtypes = [wintypes.HWND]
    u32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    return k32, u32


class _ProcessEntry(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260),
    ]


def running_processes() -> set:
    """Nomes (minúsculas) de todos os processos em execução; vazio fora do Windows."""
    if sys.platform != "win32":
        return set()
    k32, _ = _win_api()
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snap or snap == ctypes.c_void_p(-1).value:
        return set()
    names = set()
    try:
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        ok = k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            names.add(entry.szExeFile.lower())
            ok = k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snap)
    return names


def _image_name(k32, pid: int) -> str | None:
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return re.split(r"[\\/]", buf.value)[-1].lower()
    finally:
        k32.CloseHandle(handle)
    return None


def foreground_process() -> str | None:
    """Executável da janela em primeiro plano."""
    if sys.platform != "win32":
        return None
    k32, u32 = _win_api()
    hwnd = u32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return _image_name(k32, pid.value) if pid.value else None


def visible_window_processes() -> list:
    """Executáveis com janela visível: a lista que o utilizador escolhe na UI."""
    if sys.platform != "win32":
        return []
    k32, u32 = _win_api()
    found: set = set()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _lparam):
        if u32.IsWindowVisible(hwnd) and u32.GetWindowTextLengthW(hwnd) > 0:
            pid = wintypes.DWORD()
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            name = _image_name(k32, pid.value) if pid.value else None
            if name and name not in _IGNORED_WINDOW_PROCESSES:
                found.add(name)
        return True

    u32.EnumWindows(visit, 0)
    return sorted(found)


class GameWatcher:
    """Vigia os processos e avisa quando o perfil ativo muda (ou é editado)."""

    def __init__(
        self,
        store: GameProfileStore,
        on_change: Callable[[GameProfile | None], None],
        is_enabled: Callable[[], bool] = lambda: True,
        interval: float = 2.0,
        get_running: Callable[[], set] = running_processes,
        get_foreground: Callable[[], str | None] = foreground_process,
    ):
        self._store = store
        self._on_change = on_change
        self._is_enabled = is_enabled
        self._interval = interval
        self._get_running = get_running
        self._get_foreground = get_foreground
        self._current: GameProfile | None = None
        self._tick_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def current(self) -> GameProfile | None:
        return self._current

    def tick(self) -> None:
        """Uma verificação; chamável diretamente (testes, ou logo após editar perfis)."""
        with self._tick_lock:
            profiles = self._store.snapshot() if self._is_enabled() else []
            target = None
            if profiles:
                target = pick_profile(profiles, self._get_running(), self._get_foreground())
            if target != self._current:
                self._current = target
                self._on_change(target)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="game-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:  # um erro de deteção não pode matar o watcher
                pass
            self._stop.wait(self._interval)
