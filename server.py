"""
Backend WebSocket server para a UI React do WootFlow.
FastAPI + WebSocket — controla efeitos, áudio reativo, cores per-key.
"""

import asyncio
import atexit
import json
import logging
import os
import signal
import sys
import threading
import time
import traceback

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

log = logging.getLogger("wooting")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

# ── Imports do projecto ──
from utils.wooting_rgb import WootFlowRGB, WOOTING_RGB_ROWS, WOOTING_RGB_COLS
from core.effects_engine import (
    EqualizerEffect, ALL_KEYS,
    scale_color, PHYSICAL_KEYS_60HE, EQ_COLUMNS,
    apply_profile,
)
from core.devices import profile_from_device_info
import core.effects_engine as _effects_engine
from core.effect_registry import EFFECT_LABELS, EFFECT_REGISTRY
from core.analog_keys import AnalogTuning
from core.analog_live import AnalogLive
from core.rgb_sleep import normalize_minutes, sleep_factor
from audio_reactive import AudioReactive

try:
    from core.screen_ambience_profile import load_ambience_profile
    HAS_SCREEN_AMBIENCE = True
except Exception:
    HAS_SCREEN_AMBIENCE = False


# ============================================================================
# Tracked keyboard — intercepts colors for UI preview
# ============================================================================
class TrackedKeyboard:
    """Wrapper around WootFlowRGB that captures the color buffer for UI."""

    def __init__(self, kb: WootFlowRGB):
        self._kb = kb
        # Frame buffer: row → col → (r, g, b)
        self.frame: list[list[tuple[int, int, int]]] = [
            [(0, 0, 0)] * WOOTING_RGB_COLS for _ in range(WOOTING_RGB_ROWS)
        ]
        # Suspensão RGB: o frame guarda a cor original; só o hardware recebe a escalada.
        self.scale = 1.0

    def array_set_single(self, row: int, col: int, r: int, g: int, b: int) -> bool:
        if 0 <= row < WOOTING_RGB_ROWS and 0 <= col < WOOTING_RGB_COLS:
            self.frame[row][col] = (r, g, b)
        s = self.scale
        if s != 1.0:
            r, g, b = int(r * s), int(g * s), int(b * s)
        return self._kb.array_set_single(row, col, r, g, b)

    def set_scale(self, scale: float):
        """Muda o brilho de suspensão e reenvia já o frame atual."""
        if scale == self.scale:
            return
        self.scale = scale
        for row in range(WOOTING_RGB_ROWS):
            for col in range(WOOTING_RGB_COLS):
                r, g, b = self.frame[row][col]
                self._kb.array_set_single(row, col, int(r * scale), int(g * scale), int(b * scale))
        self._kb.array_update()

    def array_update(self) -> bool:
        return self._kb.array_update()

    def __getattr__(self, name):
        return getattr(self._kb, name)

# ── pynput para captura de teclado (reactive typing / ripple) ──
try:
    from pynput import keyboard as pynput_kb
    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False

try:
    import ctypes
    HAS_CTYPES = True
except Exception:
    HAS_CTYPES = False


# ============================================================================
# Tecla física (scancode) / VK → SDK (row, col)
# ============================================================================
# Priorizamos scancode para manter posição física correta entre layouts.
# VK fica como fallback quando o scancode não está disponível.

ACTIVE_KEYS = set(ALL_KEYS)
SPACE_LED_KEYS = [(5, 4), (5, 5), (5, 6), (5, 7), (5, 8)]

SCANCODE_TO_SDK = {
    # Row 1
    0x01: (1, 0),   # Esc
    0x02: (1, 1),   # 1
    0x03: (1, 2),   # 2
    0x04: (1, 3),   # 3
    0x05: (1, 4),   # 4
    0x06: (1, 5),   # 5
    0x07: (1, 6),   # 6
    0x08: (1, 7),   # 7
    0x09: (1, 8),   # 8
    0x0A: (1, 9),   # 9
    0x0B: (1, 10),  # 0
    0x0C: (1, 11),  # key between 0 and next symbol key
    0x0D: (1, 12),  # key before backspace
    0x0E: (1, 13),  # Backspace

    # Row 2
    0x0F: (2, 0),   # Tab
    0x10: (2, 1),   # Q
    0x11: (2, 2),   # W
    0x12: (2, 3),   # E
    0x13: (2, 4),   # R
    0x14: (2, 5),   # T
    0x15: (2, 6),   # Y
    0x16: (2, 7),   # U
    0x17: (2, 8),   # I
    0x18: (2, 9),   # O
    0x19: (2, 10),  # P
    0x1A: (2, 11),  # key after P
    0x1B: (2, 12),  # key before Enter area

    # Row 3
    0x3A: (3, 0),   # CapsLock
    0x1E: (3, 1),   # A
    0x1F: (3, 2),   # S
    0x20: (3, 3),   # D
    0x21: (3, 4),   # F
    0x22: (3, 5),   # G
    0x23: (3, 6),   # H
    0x24: (3, 7),   # J
    0x25: (3, 8),   # K
    0x26: (3, 9),   # L
    0x27: (3, 10),  # key after L
    0x28: (3, 11),  # key after previous
    0x29: (3, 12),  # key before Enter
    0x1C: (3, 13),  # Enter

    # Row 4
    0x2A: (4, 0),   # LShift
    0x56: (4, 1),   # ISO < key
    0x2C: (4, 2),   # Z
    0x2D: (4, 3),   # X
    0x2E: (4, 4),   # C
    0x2F: (4, 5),   # V
    0x30: (4, 6),   # B
    0x31: (4, 7),   # N
    0x32: (4, 8),   # M
    0x33: (4, 9),   # key after M
    0x34: (4, 10),  # key after previous
    0x35: (4, 11),  # key before RShift
    0x36: (4, 13),  # RShift

    # Row 5
    0x1D: (5, 0),   # Ctrl (left; right via VK fallback)
    0x38: (5, 2),   # Alt (left; right via VK fallback)
    0x39: (5, 6),   # Space (center LED)
}

VK_TO_SDK = {
    # Row 1 — Number row
    0x1B: (1, 0),   # Escape
    0x31: (1, 1),   # 1
    0x32: (1, 2),   # 2
    0x33: (1, 3),   # 3
    0x34: (1, 4),   # 4
    0x35: (1, 5),   # 5
    0x36: (1, 6),   # 6
    0x37: (1, 7),   # 7
    0x38: (1, 8),   # 8
    0x39: (1, 9),   # 9
    0x30: (1, 10),  # 0
    0xBD: (1, 11),  # -
    0xBB: (1, 12),  # =
    0x08: (1, 13),  # Backspace

    # Row 2 — QWERTY
    0x09: (2, 0),   # Tab
    0x51: (2, 1),   # Q
    0x57: (2, 2),   # W
    0x45: (2, 3),   # E
    0x52: (2, 4),   # R
    0x54: (2, 5),   # T
    0x59: (2, 6),   # Y
    0x55: (2, 7),   # U
    0x49: (2, 8),   # I
    0x4F: (2, 9),   # O
    0x50: (2, 10),  # P
    0xDB: (2, 11),  # [
    0xDD: (2, 12),  # ]

    # Row 3 — Home row
    0x14: (3, 0),   # CapsLock
    0x41: (3, 1),   # A
    0x53: (3, 2),   # S
    0x44: (3, 3),   # D
    0x46: (3, 4),   # F
    0x47: (3, 5),   # G
    0x48: (3, 6),   # H
    0x4A: (3, 7),   # J
    0x4B: (3, 8),   # K
    0x4C: (3, 9),   # L
    0xBA: (3, 10),  # ; (Ç on PT)
    0xDE: (3, 11),  # ' (º on PT)
    0xC0: (3, 12),  # ` / ~ (« on PT)
    0x0D: (3, 13),  # Enter

    # Row 4 — Shift row (ISO: col 1 = <, Z at col 2)
    0xA0: (4, 0),   # LShift
    0xE2: (4, 1),   # OEM_102 = ISO < key
    0x5A: (4, 2),   # Z
    0x58: (4, 3),   # X
    0x43: (4, 4),   # C
    0x56: (4, 5),   # V
    0x42: (4, 6),   # B
    0x4E: (4, 7),   # N
    0x4D: (4, 8),   # M
    0xBC: (4, 9),   # ,
    0xBE: (4, 10),  # .
    0xBF: (4, 11),  # /
    0xA1: (4, 13),  # RShift

    # Row 5 — Bottom row
    0xA2: (5, 0),   # LCtrl
    0x5B: (5, 1),   # LWin
    0xA4: (5, 2),   # LAlt
    0x20: (5, 6),   # Space
    0xA5: (5, 10),  # RAlt
    0x5D: (5, 11),  # Menu/Apps
    0xA3: (5, 12),  # RCtrl
}


def _get_scancode(key) -> int | None:
    """Extrai scancode físico do evento pynput (quando disponível)."""
    for source in (key, getattr(key, "value", None)):
        if source is None:
            continue
        for attr in ("scan_code", "scancode", "scan", "_scan"):
            val = getattr(source, attr, None)
            if isinstance(val, int):
                # Alguns backends colocam flags no byte alto.
                return val & 0xFF
    return None


def _get_vk(key) -> int | None:
    """Extrai virtual key code de um evento pynput."""
    if hasattr(key, "vk") and key.vk is not None:
        return key.vk
    if hasattr(key, "value") and hasattr(key.value, "vk"):
        return key.value.vk
    return None


def _get_key_pos(key) -> tuple[int, int] | None:
    """Resolve posição SDK priorizando scancode (físico), depois VK."""
    sc = _get_scancode(key)
    if sc is not None:
        mapped = SCANCODE_TO_SDK.get(sc)
        if mapped in ACTIVE_KEYS:
            return mapped

    # Alguns layouts podem expor VK ambíguo para dead-keys;
    # quando o char já vem resolvido, desambiguamos aqui.
    key_char = getattr(key, "char", None)
    if isinstance(key_char, str) and key_char == "~":
        return (3, 12)

    vk = _get_vk(key)
    if vk is None:
        return None
    mapped = VK_TO_SDK.get(vk)
    if mapped in ACTIVE_KEYS:
        return mapped
    return None


def _is_space_key_event(key, pos: tuple[int, int] | None) -> bool:
    """Deteta Space de forma robusta para expandir para os 5 LEDs."""
    if pos == (5, 6):
        return True

    sc = _get_scancode(key)
    if sc == 0x39:
        return True

    vk = _get_vk(key)
    return vk == 0x20


# ============================================================================
# Settings persistence
# ============================================================================
_base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
_runtime_base_dir = (
    os.path.dirname(os.path.abspath(sys.argv[0]))
    if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__))
)


def _resolve_settings_paths() -> tuple[str, list[str]]:
    local_appdata = os.environ.get("LOCALAPPDATA")
    user_dir = os.path.join(local_appdata or _runtime_base_dir, "WootFlow")
    user_path = os.path.join(user_dir, "rgb_settings.json")

    # Legacy locations from older builds/installations.
    legacy_paths = [
        os.path.join(_runtime_base_dir, "config", "rgb_settings.json"),
        os.path.join(_runtime_base_dir, "rgb_settings.json"),
    ]
    return user_path, legacy_paths


_settings_path, _legacy_settings_paths = _resolve_settings_paths()

_AUTOSTART_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTOSTART_VALUE_NAME = "WootFlow"


def _migrate_legacy_settings_if_needed():
    if os.path.exists(_settings_path):
        return

    for old_path in _legacy_settings_paths:
        if not os.path.exists(old_path):
            continue
        try:
            os.makedirs(os.path.dirname(_settings_path), exist_ok=True)
            with open(old_path, "r", encoding="utf-8") as src:
                payload = json.load(src)
            with open(_settings_path, "w", encoding="utf-8") as dst:
                json.dump(payload, dst, indent=2)
            log.info("Migrated settings from %s to %s", old_path, _settings_path)
            return
        except Exception as e:
            log.warning("Could not migrate settings from %s: %s", old_path, e)


_migrate_legacy_settings_if_needed()

def _load_settings() -> dict:
    """Load user settings from disk."""
    try:
        if os.path.exists(_settings_path):
            with open(_settings_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log.warning("Could not load settings: %s", e)
    return {}

def _save_settings(data: dict):
    """Save user settings to disk."""
    try:
        os.makedirs(os.path.dirname(_settings_path), exist_ok=True)
        with open(_settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log.warning("Could not save settings: %s", e)


def _autostart_supported() -> bool:
    return sys.platform == "win32"


def _build_autostart_command() -> str:
    """Build command line persisted in Windows Run registry key."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --start-hidden'

    launcher = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main_desktop.py")
    return f'"{sys.executable}" "{launcher}" --start-hidden'


def _read_windows_autostart_status() -> tuple[bool, str | None]:
    """Return (enabled, error_message)."""
    if not _autostart_supported():
        return False, None

    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_REG_PATH, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, _AUTOSTART_VALUE_NAME)
            enabled = bool(str(value).strip())
            return enabled, None
    except FileNotFoundError:
        return False, None
    except Exception as exc:
        return False, str(exc)


def _set_windows_autostart(enabled: bool) -> tuple[bool, str | None]:
    """Return (ok, error_message)."""
    if not _autostart_supported():
        return False, "Autostart not supported on this platform"

    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_REG_PATH) as key:
            if enabled:
                winreg.SetValueEx(key, _AUTOSTART_VALUE_NAME, 0, winreg.REG_SZ, _build_autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, _AUTOSTART_VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True, None
    except Exception as exc:
        return False, str(exc)


# ============================================================================
# Application state
# ============================================================================
class AppState:
    """Mantém o estado global da aplicação."""

    def __init__(self):
        self.kb = None          # WootFlowRGB (raw)
        self.tracked_kb = None  # TrackedKeyboard wrapper
        self.connected = False
        self.running = False
        self.frame_colors: dict[str, list[int]] = {}  # "row-col" → [r,g,b]
        self._prev_frame: dict[str, list[int]] = {}   # previous frame for delta
        self._device_info: dict | None = None

        # Efeito actual
        self.mode = "effect"    # "effect" | "audio" | "perkey" | "off"
        self.current_effect_name = "breathing"
        self.current_effect = None

        # Audio
        self.audio = AudioReactive()
        self.audio_running = False
        self.eq_effect = EqualizerEffect()

        # Per-key colors (6 rows x 21 cols)
        self.perkey_colors = [
            [(0, 0, 0)] * WOOTING_RGB_COLS for _ in range(WOOTING_RGB_ROWS)
        ]

        # Effect params
        self.brightness = 1.0
        self.speed = 1.0
        self.color1 = (0, 255, 200)
        self.color2 = (255, 0, 100)
        self.magnetic_influence = 3.0
        self.liquid_deform = 0.55

        # Actuation point / Rapid Trigger tuning (per key, stored locally)
        self.analog = AnalogTuning()

        # Suspensão RGB (software): minutos sem premir teclas; None = nunca
        self.sleep_dim_min: int | None = None
        self.sleep_off_min: int | None = None
        self.debounce = False  # guardado; o filtro real só existe no firmware
        self.last_activity = time.time()

        # Keyboard input listener (pynput)
        self._kb_listener = None

        self.input_caps = False

        # WebSocket clients
        self.clients: set[WebSocket] = set()
        self._thread = None
        self._transition_lock = threading.RLock()
        self._transition_seq = 0
        self.debug_mode = os.environ.get("WOOTFLOW_DEBUG", "1").lower() not in ("0", "false", "no")

        # Screen ambience profile (optional)
        self.screen_ambience = None

        # Auto-start state (Windows only)
        self.auto_start_enabled = False
        self.auto_start_supported = _autostart_supported()
        self.auto_start_error: str | None = None

        # Load saved settings
        self._load_user_settings()
        self.refresh_auto_start_state()

    def _load_user_settings(self):
        """Restore settings from disk."""
        s = _load_settings()
        if not s:
            return
        self.brightness = s.get("brightness", self.brightness)
        self.speed = s.get("speed", self.speed)
        self.color1 = tuple(s.get("color1", list(self.color1)))
        self.color2 = tuple(s.get("color2", list(self.color2)))
        self.magnetic_influence = float(s.get("magnetic_influence", self.magnetic_influence))
        self.liquid_deform = float(s.get("liquid_deform", self.liquid_deform))
        self.current_effect_name = s.get("effect", self.current_effect_name)
        self.mode = s.get("mode", self.mode)
        self.auto_start_enabled = bool(s.get("auto_start", self.auto_start_enabled))
        self.analog = AnalogTuning.from_dict(s.get("analog"))
        self.sleep_dim_min = normalize_minutes(s.get("sleep_dim_min"))
        self.sleep_off_min = normalize_minutes(s.get("sleep_off_min"))
        self.debounce = bool(s.get("debounce", self.debounce))
        log.info("Settings loaded: effect=%s brightness=%.0f%%",
                 self.current_effect_name, self.brightness * 100)

    def refresh_auto_start_state(self):
        if not self.auto_start_supported:
            self.auto_start_enabled = False
            self.auto_start_error = None
            return

        enabled, err = _read_windows_autostart_status()
        self.auto_start_enabled = enabled
        self.auto_start_error = err

    def set_auto_start_enabled(self, enabled: bool) -> bool:
        if not self.auto_start_supported:
            self.auto_start_enabled = False
            self.auto_start_error = "Autostart not supported on this platform"
            return False

        ok, err = _set_windows_autostart(bool(enabled))
        self.auto_start_error = err
        if ok:
            self.auto_start_enabled = bool(enabled)
            self.save_settings()
            return True

        # Keep state aligned with the actual registry state in case of write failure.
        self.refresh_auto_start_state()
        return False

    def _debug_log(self, message: str, **fields):
        if not self.debug_mode:
            return
        if fields:
            details = " ".join(f"{k}={fields[k]!r}" for k in sorted(fields))
            log.info("[DEBUG] %s | %s", message, details)
        else:
            log.info("[DEBUG] %s", message)

    def _active_threads(self) -> list[str]:
        return [t.name for t in threading.enumerate() if t.is_alive()]

    def _is_screen_ambience_active(self) -> bool:
        return bool(self.screen_ambience and getattr(self.screen_ambience, "is_active", False))

    def _clear_preview_cache(self):
        self.frame_colors = {}
        self._prev_frame = {}

    def _wait_effects_drained(self, timeout: float = 1.5) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.audio_running and not self._is_screen_ambience_active():
                return True
            time.sleep(0.02)
        return False

    def _stop_active_effects_locked(self, reason: str):
        self._debug_log(
            "Stopping active effects",
            reason=reason,
            mode=self.mode,
            effect=self.current_effect_name,
            audio_running=self.audio_running,
            screen_ambience=self._is_screen_ambience_active(),
        )

        if self._is_screen_ambience_active():
            self._disable_screen_ambience()

        if self.audio_running:
            self.audio.stop()
            self.audio_running = False

        self.current_effect = None
        self._clear_preview_cache()

    def _transition_to_locked(self, target_mode: str, effect_name: str | None = None) -> bool:
        self._transition_seq += 1
        transition_id = self._transition_seq
        self._debug_log(
            "Transition begin",
            id=transition_id,
            target_mode=target_mode,
            target_effect=effect_name,
            thread_count=len(self._active_threads()),
        )

        self._stop_active_effects_locked(reason=f"transition-{transition_id}")
        if not self._wait_effects_drained(timeout=1.5):
            log.error(
                "[ERROR] Effect overlap detected: previous workers still active before transition id=%s",
                transition_id,
            )

        ok = True
        if target_mode == "effect":
            name = (effect_name or self.current_effect_name or "breathing").strip()
            if name == "screen_ambience":
                ok = self._enable_screen_ambience()
                if ok:
                    self.mode = "effect"
                    self.current_effect_name = "screen_ambience"
                    self.current_effect = None
            elif name in EFFECT_REGISTRY:
                self.current_effect_name = name
                self.current_effect = EFFECT_REGISTRY[name]()
                self.current_effect.brightness = self.brightness
                self.current_effect._base_speed = self.current_effect.speed
                self.current_effect.speed = self.current_effect._base_speed * self.speed
                self.current_effect.color1 = self.color1
                self.current_effect.color2 = self.color2
                if hasattr(self.current_effect, "influence"):
                    self.current_effect.influence = self.magnetic_influence
                if hasattr(self.current_effect, "deform_strength"):
                    self.current_effect.deform_strength = self.liquid_deform
                self.mode = "effect"
            else:
                ok = False
        elif target_mode == "audio":
            ok = self.audio.start()
            self.audio_running = bool(ok)
            if ok:
                self.mode = "audio"
                self.eq_effect.brightness = self.brightness
            else:
                self.mode = "effect"
        elif target_mode == "perkey":
            self.mode = "perkey"
            self.current_effect_name = "perkey"
            self.current_effect = None
        elif target_mode == "off":
            self.mode = "off"
            self.current_effect_name = "off"
            self.current_effect = None
        else:
            ok = False

        self._debug_log(
            "Transition end",
            id=transition_id,
            ok=ok,
            mode=self.mode,
            effect=self.current_effect_name,
            audio_running=self.audio_running,
            screen_ambience=self._is_screen_ambience_active(),
            thread_count=len(self._active_threads()),
        )
        return ok

    def transition_to(self, target_mode: str, effect_name: str | None = None) -> bool:
        with self._transition_lock:
            # Sempre desativa o efeito anterior antes de ativar o novo
            if self.mode == "effect":
                if self.current_effect_name == "screen_ambience":
                    self._disable_screen_ambience()
                elif self.current_effect is not None:
                    try:
                        if hasattr(self.current_effect, "deactivate"):
                            self.current_effect.deactivate()
                    except Exception:
                        pass
                    self.current_effect = None
            return self._transition_to_locked(target_mode, effect_name)

    def _enforce_runtime_invariants_locked(self):
        if self.mode != "audio" and self.audio_running:
            log.error("[ERROR] Effect overlap detected: audio_running=True while mode=%s", self.mode)
            self.audio.stop()
            self.audio_running = False

        if self._is_screen_ambience_active() and not (
            self.mode == "effect" and self.current_effect_name == "screen_ambience"
        ):
            log.error(
                "[ERROR] Effect overlap detected: screen ambience active while mode=%s effect=%s",
                self.mode,
                self.current_effect_name,
            )
            self._disable_screen_ambience()

        if self.current_effect_name == "screen_ambience" and self.current_effect is not None:
            log.error("[ERROR] Invalid state: screen_ambience selected with non-null current_effect")
            self.current_effect = None

    def save_settings(self):
        """Persist current settings to disk."""
        _save_settings({
            "brightness": self.brightness,
            "speed": self.speed,
            "color1": list(self.color1),
            "color2": list(self.color2),
            "magnetic_influence": self.magnetic_influence,
            "liquid_deform": self.liquid_deform,
            "effect": self.current_effect_name,
            "mode": self.mode,
            "auto_start": self.auto_start_enabled,
            "analog": self.analog.to_dict(),
            "sleep_dim_min": self.sleep_dim_min,
            "sleep_off_min": self.sleep_off_min,
            "debounce": self.debounce,
        })

    def connect_keyboard(self) -> bool:
        try:
            self.kb = WootFlowRGB()
            if self.kb.is_connected():
                self.tracked_kb = TrackedKeyboard(self.kb)
                self.connected = True
                try:
                    self._device_info = self.kb.get_device_info()
                except Exception:
                    self._device_info = None
                self._adapt_to_device()
                log.info("Keyboard connected: %s", _effects_engine.ACTIVE_PROFILE.name)
                return True
            else:
                log.warning("Keyboard not found")
        except Exception as e:
            log.error("Connection error: %s", e)
        self.connected = False
        self._device_info = None
        return False

    def _adapt_to_device(self):
        """Ajusta o layout dos efeitos ao teclado detetado."""
        profile = profile_from_device_info(self._device_info)
        previous = _effects_engine.ACTIVE_PROFILE
        if profile == previous:
            return
        apply_profile(profile)
        self.eq_effect = EqualizerEffect()
        if (self.mode == "effect" and self.current_effect is not None
                and self.current_effect_name != "screen_ambience"):
            self.transition_to("effect", self.current_effect_name)

    def disconnect_keyboard(self):
        """Cleanly disconnect the keyboard."""
        if self.kb:
            try:
                self.kb.reset()
                self.kb.close()
            except Exception:
                pass
        self.kb = None
        self.tracked_kb = None
        self.connected = False
        self._device_info = None

    def set_effect(self, name: str):
        return self.transition_to("effect", name)

    def _enable_screen_ambience(self) -> bool:
        """Ativa Screen Ambience como um efeito selecionável na UI."""
        if not HAS_SCREEN_AMBIENCE:
            return False
        try:
            if self.screen_ambience is None:
                profile_dir = os.path.join(_base_dir, "profiles")
                self.screen_ambience = load_ambience_profile(self.tracked_kb, profile_dir=profile_dir)
            self.screen_ambience.activate()
            self.current_effect_name = "screen_ambience"
            self.current_effect = None
            self.mode = "effect"
            return True
        except Exception:
            log.exception("Failed to enable Screen Ambience")
            self.screen_ambience = None
            return False

    def _disable_screen_ambience(self):
        if self.screen_ambience:
            try:
                self._debug_log("Stopping effect: ScreenAmbience")
                self.screen_ambience.deactivate()
            except Exception:
                pass

    def start_audio(self) -> bool:
        return self.transition_to("audio")

    def stop_audio(self):
        with self._transition_lock:
            if self.audio_running:
                self._debug_log("Stopping effect: AudioReactive")
                self.audio.stop()
            self.audio_running = False

    def start_keyboard_listener(self):
        """Inicia o listener de teclado para reactive typing / ripple."""
        if not HAS_PYNPUT or self._kb_listener is not None:
            return
        def on_press(key):
            self.last_activity = time.time()
            pos = _get_key_pos(key)
            if pos is None:
                return
            if self.current_effect and hasattr(self.current_effect, "trigger"):
                if _is_space_key_event(key, pos):
                    for row, col in SPACE_LED_KEYS:
                        self.current_effect.trigger(row, col)
                else:
                    row, col = pos
                    self.current_effect.trigger(row, col)

        def on_release(key):
            self.last_activity = time.time()

        self._kb_listener = pynput_kb.Listener(on_press=on_press, on_release=on_release)
        self._kb_listener.daemon = True
        self._kb_listener.start()

    def stop_keyboard_listener(self):
        if self._kb_listener:
            self._kb_listener.stop()
            self._kb_listener = None

    def start_loop(self):
        if self.running:
            return
        self.running = True
        self.start_keyboard_listener()
        self._thread = threading.Thread(target=self._main_loop, daemon=True)
        self._thread.start()

    def stop_loop(self):
        self.running = False
        with self._transition_lock:
            self._stop_active_effects_locked(reason="loop-stop")
        self.stop_keyboard_listener()
        if self._thread:
            self._thread.join(timeout=2)

    def _main_loop(self):
        """Loop principal ~60fps — atualiza efeitos no teclado."""
        frame_time = 1 / 60
        while self.running:
            start = time.perf_counter()
            now = time.time()

            try:
                if not self.connected:
                    self.connect_keyboard()
                    if not self.connected:
                        time.sleep(1)
                        continue

                tkb = self.tracked_kb
                tkb.set_scale(sleep_factor(
                    now - self.last_activity, self.sleep_dim_min, self.sleep_off_min,
                ))

                with self._transition_lock:
                    self._enforce_runtime_invariants_locked()
                    mode = self.mode
                    current_effect = self.current_effect
                    current_effect_name = self.current_effect_name
                    audio_running = self.audio_running

                if mode == "off":
                    # Turn off all LEDs
                    for row in range(WOOTING_RGB_ROWS):
                        for col in range(WOOTING_RGB_COLS):
                            tkb.array_set_single(row, col, 0, 0, 0)
                    tkb.array_update()

                elif mode == "audio" and audio_running:
                    bands = self.audio.get_bands()
                    peaks = self.audio.get_peaks()
                    self.eq_effect.set_bands(bands, peaks)
                    self.eq_effect.update(tkb, now)

                elif mode == "effect" and current_effect:
                    current_effect.update(tkb, now)

                elif mode == "effect" and current_effect_name == "screen_ambience":
                    # Screen ambience updates are pushed asynchronously by its own engine.
                    pass

                elif mode == "perkey":
                    for row in range(WOOTING_RGB_ROWS):
                        for col in range(WOOTING_RGB_COLS):
                            r, g, b = self.perkey_colors[row][col]
                            tkb.array_set_single(row, col, r, g, b)
                    tkb.array_update()

                # Sample OS CapsLock state each frame so external changes
                # (other apps toggling Caps) are reflected immediately.
                if HAS_CTYPES:
                    try:
                        new_caps = bool(ctypes.windll.user32.GetKeyState(0x14) & 1)
                        prev = getattr(self, "_prev_caps_state", None)
                        if new_caps != prev:
                            log.info("CapsLock state: %s", "ON" if new_caps else "OFF")
                            self._prev_caps_state = new_caps
                        self.input_caps = new_caps
                    except Exception:
                        pass

                # If CapsLock is active, override only the Caps key to static white
                # after the effect/frame update, and commit to hardware.
                try:
                    if self.input_caps:
                        # Use array_set_single so both tracked frame and SDK buffer are updated.
                        tkb.array_set_single(3, 0, 255, 255, 255)
                        tkb.array_update()
                except Exception:
                    pass

                # Capture frame for UI preview
                self._capture_frame(tkb)
            except Exception:
                log.exception("Main loop error")
                # If keyboard disconnected mid-frame, mark as disconnected
                try:
                    if self.kb and not self.kb.is_connected():
                        self.connected = False
                        self._device_info = None
                        log.warning("Keyboard disconnected")
                except Exception:
                    self.connected = False

            elapsed = time.perf_counter() - start
            sleep_t = frame_time - elapsed
            if sleep_t > 0:
                time.sleep(sleep_t)

    def _capture_frame(self, tkb: TrackedKeyboard):
        """Copy tracked frame into serializable dict."""
        colors = {}
        for row in range(WOOTING_RGB_ROWS):
            for col in range(_effects_engine.LAYOUT_COLS):
                r, g, b = tkb.frame[row][col]
                if r or g or b:
                    colors[f"{row}-{col}"] = [r, g, b]
        self.frame_colors = colors

    def get_frame_delta(self) -> dict | None:
        """Return only changed keys since last call, or None if no changes."""
        cur = self.frame_colors
        prev = self._prev_frame
        delta = {}
        all_keys = set(cur.keys()) | set(prev.keys())
        for k in all_keys:
            c = cur.get(k)
            p = prev.get(k)
            if c != p:
                delta[k] = c if c else [0, 0, 0]
        self._prev_frame = dict(cur)
        if not delta:
            return None
        return {"type": "frame", "colors": delta, "delta": True}

    def get_full_frame(self) -> dict:
        """Full frame for initial sync."""
        self._prev_frame = dict(self.frame_colors)
        return {"type": "frame", "colors": self.frame_colors, "delta": False}

    def get_state_dict(self) -> dict:
        """Estado completo para enviar aos clientes."""
        effect_items = list(EFFECT_LABELS.items())
        if HAS_SCREEN_AMBIENCE:
            effect_items.append(("screen_ambience", "Screen Ambience"))

        d = {
            "type": "state",
            "connected": self.connected,
            "mode": self.mode,
            "effect": self.current_effect_name,
            "effects": effect_items,
            "brightness": self.brightness,
            "speed": self.speed,
            "color1": list(self.color1),
            "color2": list(self.color2),
            "effectParams": {
                "magneticInfluence": self.magnetic_influence,
                "liquidDeform": self.liquid_deform,
            },
            "audioRunning": self.audio_running,
            "audioAvailable": AudioReactive.available(),
            "pynputAvailable": HAS_PYNPUT,
            "capsLock": bool(self.input_caps),
            "debugMode": self.debug_mode,
            "autoStartEnabled": self.auto_start_enabled,
            "autoStartSupported": self.auto_start_supported,
            "analog": self.analog.to_dict(),
            "sleepDimMin": self.sleep_dim_min,
            "sleepOffMin": self.sleep_off_min,
            "debounce": self.debounce,
        }
        if self.auto_start_error:
            d["autoStartError"] = self.auto_start_error
        if self._device_info:
            d["device"] = {
                "model": self._device_info.get("model", "Unknown"),
                "layout": self._device_info.get("layout", "Unknown"),
                **_effects_engine.ACTIVE_PROFILE.to_dict(),
            }
        return d

    def get_audio_dict(self) -> dict | None:
        """Dados de áudio para streaming."""
        if not self.audio_running:
            return None
        return {
            "type": "audio",
            "bands": self.audio.get_bands(),
            "peaks": self.audio.get_peaks(),
            "volume": self.audio.get_volume(),
        }

    def get_debug_snapshot(self) -> dict:
        with self._transition_lock:
            threads = self._active_threads()
            return {
                "type": "debug",
                "mode": self.mode,
                "effect": self.current_effect_name,
                "audioRunning": self.audio_running,
                "screenAmbienceActive": self._is_screen_ambience_active(),
                "activeThreads": threads,
                "threadCount": len(threads),
            }


# ============================================================================
# FastAPI app
# ============================================================================
state = AppState()
_cleanup_done = False


def _force_cleanup():
    """Garantir que o SDK liberta o teclado em qualquer cenário de saída."""
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True
    log.info("Cleaning up keyboard SDK...")
    try:
        state.save_settings()
    except Exception:
        pass
    try:
        state.stop_loop()
    except Exception:
        pass
    try:
        state.transition_to("off")
    except Exception:
        pass
    if state.kb:
        try:
            state.kb.reset()
        except Exception:
            pass
        try:
            state.kb.close()
        except Exception:
            pass
        state.kb = None
        state.tracked_kb = None
        state.connected = False
    log.info("Keyboard SDK released.")


# Registar cleanup para QUALQUER forma de saída do processo
atexit.register(_force_cleanup)


def _signal_shutdown(signum, frame):
    """Handle SIGINT/SIGTERM — cleanup and exit."""
    _force_cleanup()
    sys.exit(0)


signal.signal(signal.SIGINT, _signal_shutdown)
signal.signal(signal.SIGTERM, _signal_shutdown)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        log.info("=== FastAPI lifespan startup ===")
        log.info("Connecting to keyboard...")
        state.connect_keyboard()
        log.info("✓ Keyboard connected")
        
        log.info("Setting effect...")
        state.set_effect(state.current_effect_name)
        log.info("✓ Effect set")
        
        log.info("Starting main loop...")
        state.start_loop()
        log.info("✓ Main loop started")
        log.info("=== App ready for requests ===")
    except Exception as _exc:
        log.exception("CRITICAL: Lifespan startup failed: %s", _exc)
        log.error("Full traceback: %s", traceback.format_exc())
        raise
    
    yield
    
    # Shutdown (graceful via uvicorn)
    try:
        log.info("=== FastAPI lifespan shutdown ===")
        _force_cleanup()
        log.info("✓ Cleanup complete")
    except Exception as _exc:
        log.exception("Error during shutdown: %s", _exc)


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:9120", "http://localhost:9120"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health endpoint usado pelo launcher para validar readiness local."""
    return {
        "ok": True,
        "service": "WootFlow",
        "websocket": "/ws",
        "connected": state.connected,
    }


# ── WebSocket (must be registered BEFORE static files mount) ──
analog_live = AnalogLive()
live_clients: set = set()


def _set_live(ws, enabled: bool) -> bool:
    """Liga/desliga a leitura de profundidade das teclas para um cliente."""
    if enabled and ws not in live_clients:
        if not analog_live.acquire():
            return False
        live_clients.add(ws)
    elif not enabled and ws in live_clients:
        live_clients.discard(ws)
        analog_live.release()
    return True


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    state.clients.add(ws)

    # Enviar estado inicial + full frame
    await ws.send_json(state.get_state_dict())
    if state.frame_colors:
        await ws.send_json(state.get_full_frame())

    # Tarefa de push: profundidade das teclas ~30fps, frame e áudio ~15fps
    async def data_push():
        tick = 0
        last_keys = None
        while True:
            try:
                if ws in live_clients:
                    keys = analog_live.snapshot()
                    if keys != last_keys:
                        last_keys = dict(keys)
                        await ws.send_json({"type": "analog_live", "keys": last_keys})
                if tick % 2 == 0:
                    if state.connected:
                        delta = state.get_frame_delta()
                        if delta:
                            await ws.send_json(delta)
                    if state.audio_running:
                        data = state.get_audio_dict()
                        if data:
                            await ws.send_json(data)
                tick += 1
                await asyncio.sleep(1 / 30)
            except Exception:
                break

    push_task = asyncio.create_task(data_push())

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            await handle_message(ws, msg)
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("WebSocket error")
    finally:
        push_task.cancel()
        _set_live(ws, False)
        state.clients.discard(ws)


async def broadcast(data: dict):
    """Envia para todos os clientes conectados."""
    dead = set()
    for ws in state.clients:
        try:
            await ws.send_json(data)
        except Exception:
            dead.add(ws)
    state.clients -= dead


async def handle_message(ws: WebSocket, msg: dict):
    """Processa mensagens recebidas do frontend."""
    action = msg.get("action")
    try:
        log.info("WS message received: %s", json.dumps(msg))
    except Exception:
        log.info("WS message received (unserializable)")

    if action == "get_state":
        await ws.send_json(state.get_state_dict())

    elif action == "get_debug_stats":
        await ws.send_json(state.get_debug_snapshot())

    elif action == "set_effect":
        name = msg.get("name", "")
        if state.transition_to("effect", name):
            state.save_settings()
            await broadcast(state.get_state_dict())
            # Forçar envio de full frame para todos os clientes após troca de efeito
            await broadcast(state.get_full_frame())

    elif action == "start_audio":
        if state.transition_to("audio"):
            state.save_settings()
            await broadcast(state.get_state_dict())

    elif action == "stop_audio":
        fallback_effect = state.current_effect_name if state.current_effect_name in EFFECT_REGISTRY else "breathing"
        state.transition_to("effect", fallback_effect)
        state.save_settings()
        await broadcast(state.get_state_dict())

    elif action == "set_brightness":
        val = max(0.0, min(1.0, float(msg.get("value", 1.0))))
        state.brightness = val
        if state.current_effect:
            state.current_effect.brightness = val
        state.eq_effect.brightness = val
        state.save_settings()
        await broadcast(state.get_state_dict())

    elif action == "set_speed":
        val = max(0.1, min(5.0, float(msg.get("value", 1.0))))
        state.speed = val
        if state.current_effect:
            base = getattr(state.current_effect, "_base_speed", None)
            state.current_effect.speed = (base if base is not None else 1.0) * val
        state.save_settings()
        await broadcast(state.get_state_dict())

    elif action == "set_color1":
        c = msg.get("color", [0, 255, 200])
        state.color1 = tuple(max(0, min(255, int(v))) for v in c[:3])
        if state.current_effect:
            state.current_effect.color1 = state.color1
        state.save_settings()
        await broadcast(state.get_state_dict())

    elif action == "set_color2":
        c = msg.get("color", [255, 0, 100])
        state.color2 = tuple(max(0, min(255, int(v))) for v in c[:3])
        if state.current_effect:
            state.current_effect.color2 = state.color2
        state.save_settings()
        await broadcast(state.get_state_dict())

    elif action == "set_effect_param":
        param = str(msg.get("param", "")).strip()
        value = float(msg.get("value", 0.0))

        if param == "magneticInfluence":
            state.magnetic_influence = max(1.2, min(6.0, value))
            if state.current_effect and hasattr(state.current_effect, "influence"):
                state.current_effect.influence = state.magnetic_influence
            state.save_settings()
            await broadcast(state.get_state_dict())

        elif param == "liquidDeform":
            state.liquid_deform = max(0.0, min(1.5, value))
            if state.current_effect and hasattr(state.current_effect, "deform_strength"):
                state.current_effect.deform_strength = state.liquid_deform
            state.save_settings()
            await broadcast(state.get_state_dict())

    elif action == "set_perkey":
        row = int(msg.get("row", 0))
        col = int(msg.get("col", 0))
        c = msg.get("color", [255, 255, 255])
        if 0 <= row < WOOTING_RGB_ROWS and 0 <= col < WOOTING_RGB_COLS:
            state.perkey_colors[row][col] = tuple(
                max(0, min(255, int(v))) for v in c[:3]
            )

    elif action == "set_all_perkey":
        c = msg.get("color", [255, 255, 255])
        color = tuple(max(0, min(255, int(v))) for v in c[:3])
        for row in range(WOOTING_RGB_ROWS):
            for col in range(WOOTING_RGB_COLS):
                state.perkey_colors[row][col] = color

    elif action == "set_audio_sensitivity":
        val = max(0.1, min(5.0, float(msg.get("value", 1.5))))
        state.audio.sensitivity = val

    elif action == "set_audio_smoothing":
        val = max(0.0, min(0.95, float(msg.get("value", 0.3))))
        state.audio.smoothing = val

    elif action == "set_mode":
        mode = msg.get("mode", "effect")
        if mode in ("effect", "audio", "perkey", "off"):
            if mode == "audio":
                state.transition_to("audio")
            elif mode == "effect":
                fallback_effect = state.current_effect_name if state.current_effect_name in EFFECT_REGISTRY else "breathing"
                state.transition_to("effect", fallback_effect)
            else:
                state.transition_to(mode)
            state.save_settings()
            await broadcast(state.get_state_dict())

    elif action == "set_analog":
        raw_keys = msg.get("keys", [])
        key_ids = [k for k in raw_keys if isinstance(k, str) and len(k) < 8][:128]
        patch = msg.get("patch", {})
        if isinstance(patch, dict):
            state.analog.apply(key_ids, patch)
        if "tachyon" in msg:
            state.analog.tachyon = bool(msg["tachyon"])
        state.save_settings()
        await broadcast(state.get_state_dict())

    elif action == "set_sleep":
        if "dim_min" in msg:
            state.sleep_dim_min = normalize_minutes(msg["dim_min"])
        if "off_min" in msg:
            state.sleep_off_min = normalize_minutes(msg["off_min"])
        # O brilho reduzido nunca pode vir depois de apagar.
        dim, off = state.sleep_dim_min, state.sleep_off_min
        if dim is not None and off is not None and dim > off:
            if "off_min" in msg and "dim_min" not in msg:
                state.sleep_dim_min = off
            else:
                state.sleep_off_min = dim
        state.last_activity = time.time()
        state.save_settings()
        await broadcast(state.get_state_dict())

    elif action == "set_debounce":
        state.debounce = bool(msg.get("enabled"))
        state.save_settings()
        await broadcast(state.get_state_dict())

    elif action == "analog_live":
        if not _set_live(ws, bool(msg.get("enabled"))):
            await ws.send_json({"type": "analog_live", "keys": {}, "error": analog_live.error})

    elif action == "reconnect":
        state.disconnect_keyboard()
        state.connect_keyboard()
        await broadcast(state.get_state_dict())

    elif action == "set_auto_start":
        enabled = bool(msg.get("enabled", False))
        state.set_auto_start_enabled(enabled)
        await broadcast(state.get_state_dict())

    elif action == "reset_perkey":
        state.perkey_colors = [
            [(0, 0, 0)] * WOOTING_RGB_COLS for _ in range(WOOTING_RGB_ROWS)
        ]
        await broadcast(state.get_state_dict())


# ── Static files (built React app) — AFTER all routes ──
_base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
ui_dist = os.path.join(_base_dir, "ui", "dist")
if os.path.isdir(ui_dist):
    app.mount("/", StaticFiles(directory=ui_dist, html=True), name="ui")


# ============================================================================
# Entry point
# ============================================================================
def main():
    import uvicorn
    print("🎹 WootFlow Server — http://localhost:9120")
    print("   WebSocket: ws://localhost:9120/ws")
    uvicorn.run(app, host="127.0.0.1", port=9120, log_level="warning")


if __name__ == "__main__":
    main()
