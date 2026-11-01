"""Leitura ao vivo da profundidade das teclas via Wooting Analog SDK.

Só lê: nunca escreve no teclado. A DLL é a instalada em
`C:\\Program Files\\wooting-analog-sdk`; os símbolos usados constam da tabela de
exportações da DLL, a assinatura C segue a API pública do SDK.
"""
from __future__ import annotations

import ctypes
import logging
import os
import threading
import time
from ctypes import POINTER, c_float, c_int, c_uint, c_ushort

log = logging.getLogger("wooting")

SDK_DIRS = (
    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "wooting-analog-sdk"),
)
KEYCODE_MODE_HID = 0   # WootingAnalog_KeycodeType_HID
BUFFER_LEN = 64
POLL_HZ = 60
MIN_DEPTH = 0.01       # abaixo disto a tecla conta como solta

# Códigos HID (usage page 0x07) -> ids "row-col" do layout 60HE ISO PT da UI.
# A barra de espaço tem 5 LEDs (cols 4..8) e acende todos.
_SPACE = ["5-4", "5-5", "5-6", "5-7", "5-8"]
HID_TO_KEY_IDS: dict[int, list[str]] = {
    41: ["1-0"],                                            # Esc
    **{30 + i: [f"1-{1 + i}"] for i in range(9)},           # 1..9
    39: ["1-10"],                                           # 0
    45: ["1-11"], 46: ["1-12"], 42: ["1-13"],               # ' « Backspace
    43: ["2-0"],                                            # Tab
    20: ["2-1"], 26: ["2-2"], 8: ["2-3"], 21: ["2-4"], 23: ["2-5"],
    28: ["2-6"], 24: ["2-7"], 12: ["2-8"], 18: ["2-9"], 19: ["2-10"],  # Q..P
    47: ["2-11"], 48: ["2-12"], 40: ["3-13"],               # + ´ Enter
    57: ["3-0"],                                            # Caps
    4: ["3-1"], 22: ["3-2"], 7: ["3-3"], 9: ["3-4"], 10: ["3-5"],
    11: ["3-6"], 13: ["3-7"], 14: ["3-8"], 15: ["3-9"],     # A..L
    51: ["3-10"], 52: ["3-11"], 50: ["3-12"],               # Ç º ~
    225: ["4-0"], 100: ["4-1"],                             # L-Shift, <
    29: ["4-2"], 27: ["4-3"], 6: ["4-4"], 25: ["4-5"], 5: ["4-6"],
    17: ["4-7"], 16: ["4-8"],                               # Z X C V B N M
    54: ["4-9"], 55: ["4-10"], 56: ["4-11"], 229: ["4-13"], # , . - R-Shift
    224: ["5-0"], 227: ["5-1"], 226: ["5-2"], 44: _SPACE,   # L-Ctrl Win Alt Space
    230: ["5-10"], 101: ["5-11"], 228: ["5-12"],            # AltGr Menu R-Ctrl
}


def depths_to_key_ids(codes, values) -> dict[str, float]:
    """Converte pares (código HID, profundidade 0..1) em {id da tecla: profundidade}."""
    out: dict[str, float] = {}
    for code, value in zip(codes, values):
        depth = max(0.0, min(1.0, float(value)))
        if depth < MIN_DEPTH:
            continue
        for key_id in HID_TO_KEY_IDS.get(int(code), ()):
            out[key_id] = round(depth, 3)
    return out


class AnalogLive:
    """Thread de leitura do buffer analógico, ligada só enquanto há quem a use."""

    def __init__(self):
        self._lib = None
        self._lock = threading.Lock()
        self._users = 0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._keys: dict[str, float] = {}
        self.error: str | None = None

    def _load(self) -> bool:
        if self._lib is not None:
            return True
        for folder in SDK_DIRS:
            path = os.path.join(folder, "wooting_analog_sdk.dll")
            if not os.path.exists(path):
                continue
            try:
                lib = ctypes.CDLL(path)
                lib.wooting_analog_initialise.restype = c_int
                lib.wooting_analog_set_keycode_mode.argtypes = [c_int]
                lib.wooting_analog_set_keycode_mode.restype = c_int
                lib.wooting_analog_read_full_buffer.argtypes = [POINTER(c_ushort), POINTER(c_float), c_uint]
                lib.wooting_analog_read_full_buffer.restype = c_int
                self._lib = lib
                return True
            except (OSError, AttributeError) as exc:
                self.error = f"Wooting Analog SDK: {exc}"
                log.warning(self.error)
        self.error = self.error or "Wooting Analog SDK não encontrado"
        return False

    def acquire(self) -> bool:
        """Pede leitura ao vivo; devolve False se o SDK não está disponível."""
        with self._lock:
            if not self._load():
                return False
            self._users += 1
            if self._thread is None or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(target=self._run, name="analog-live", daemon=True)
                self._thread.start()
            return True

    def release(self):
        with self._lock:
            self._users = max(0, self._users - 1)
            if self._users == 0:
                self._stop.set()

    def snapshot(self) -> dict[str, float]:
        return self._keys

    def _run(self):
        lib = self._lib
        devices = lib.wooting_analog_initialise()
        if devices < 0:
            self.error = f"initialise falhou ({devices})"
            log.warning("Analog SDK: %s", self.error)
            return
        lib.wooting_analog_set_keycode_mode(KEYCODE_MODE_HID)
        codes = (c_ushort * BUFFER_LEN)()
        values = (c_float * BUFFER_LEN)()
        period = 1.0 / POLL_HZ
        try:
            while not self._stop.is_set():
                n = lib.wooting_analog_read_full_buffer(codes, values, BUFFER_LEN)
                self._keys = depths_to_key_ids(codes[:n], values[:n]) if n > 0 else {}
                time.sleep(period)
        finally:
            self._keys = {}
