"""
Wrapper Python para o Wooting RGB SDK usando ctypes.
Comunica diretamente com a DLL do Wooting RGB SDK.
"""

import ctypes
import os
import sys
from ctypes import c_bool, c_int32, c_uint8, POINTER, Structure, c_char_p


# Constantes do teclado
WOOTING_RGB_ROWS = 6
WOOTING_RGB_COLS = 21


class WootingUSBMeta(Structure):
    """Struct com informações do dispositivo conectado (SDK completo)."""
    _fields_ = [
        ("connected", c_bool),
        ("model", c_char_p),
        ("max_rows", c_uint8),
        ("max_columns", c_uint8),
        ("led_index_max", c_uint8),
        # Os enums do SDK em C ocupam 4 bytes (sdk/wooting-usb.h); com 1 byte lia-se o padding.
        ("device_type", c_int32),     # WOOTING_DEVICE_TYPE enum
        ("v2_interface", c_bool),
        ("layout", c_int32),          # WOOTING_DEVICE_LAYOUT enum (0=ANSI, 1=ISO)
        ("uses_small_packets", c_bool),
        ("uses_multi_report", c_bool),
    ]


class WootFlowRGB:
    """Interface Python para o Wooting RGB SDK."""

    def __init__(self, dll_path=None):
        if dll_path is None:
            if sys.maxsize > 2**32:
                dll_name = "wooting-rgb-sdk64.dll"
            else:
                dll_name = "wooting-rgb-sdk.dll"

            search_roots = []
            if getattr(sys, "frozen", False):
                search_roots.extend([
                    getattr(sys, "_MEIPASS", ""),
                    os.path.dirname(os.path.abspath(sys.executable)),
                ])
            else:
                module_dir = os.path.dirname(os.path.abspath(__file__))
                search_roots.extend([
                    module_dir,
                    os.path.dirname(module_dir),
                    os.getcwd(),
                ])

            dll_candidates = []
            for root in search_roots:
                if not root:
                    continue
                dll_candidates.append(os.path.join(root, "sdk", dll_name))
                dll_candidates.append(os.path.join(root, dll_name))

            dll_path = next((path for path in dll_candidates if os.path.exists(path)), dll_candidates[0])

        if not os.path.exists(dll_path):
            raise FileNotFoundError(
                f"DLL não encontrada: {dll_path}\n"
                f"Baixe o SDK em: https://github.com/WootingKb/wooting-rgb-sdk/releases\n"
                f"Extraia os arquivos na pasta 'sdk/' do projeto."
            )

        self._sdk = ctypes.CDLL(dll_path)
        self._setup_functions()
        self._connected = False

    def _setup_functions(self):
        """Configura os tipos de retorno e argumentos das funções do SDK."""
        # wooting_rgb_kbd_connected
        self._sdk.wooting_rgb_kbd_connected.restype = c_bool
        self._sdk.wooting_rgb_kbd_connected.argtypes = []

        # wooting_rgb_reset_rgb
        self._sdk.wooting_rgb_reset_rgb.restype = c_bool
        self._sdk.wooting_rgb_reset_rgb.argtypes = []

        # wooting_rgb_close
        self._sdk.wooting_rgb_close.restype = c_bool
        self._sdk.wooting_rgb_close.argtypes = []

        # wooting_rgb_reset
        self._sdk.wooting_rgb_reset.restype = c_bool
        self._sdk.wooting_rgb_reset.argtypes = []

        # wooting_rgb_direct_set_key
        self._sdk.wooting_rgb_direct_set_key.restype = c_bool
        self._sdk.wooting_rgb_direct_set_key.argtypes = [c_uint8, c_uint8, c_uint8, c_uint8, c_uint8]

        # wooting_rgb_direct_reset_key
        self._sdk.wooting_rgb_direct_reset_key.restype = c_bool
        self._sdk.wooting_rgb_direct_reset_key.argtypes = [c_uint8, c_uint8]

        # wooting_rgb_array_update_keyboard
        self._sdk.wooting_rgb_array_update_keyboard.restype = c_bool
        self._sdk.wooting_rgb_array_update_keyboard.argtypes = []

        # wooting_rgb_array_auto_update
        self._sdk.wooting_rgb_array_auto_update.restype = None
        self._sdk.wooting_rgb_array_auto_update.argtypes = [c_bool]

        # wooting_rgb_array_set_single
        self._sdk.wooting_rgb_array_set_single.restype = c_bool
        self._sdk.wooting_rgb_array_set_single.argtypes = [c_uint8, c_uint8, c_uint8, c_uint8, c_uint8]

        # wooting_rgb_array_set_full
        self._sdk.wooting_rgb_array_set_full.restype = c_bool
        self._sdk.wooting_rgb_array_set_full.argtypes = [POINTER(c_uint8)]

        # wooting_rgb_device_info
        self._sdk.wooting_rgb_device_info.restype = POINTER(WootingUSBMeta)
        self._sdk.wooting_rgb_device_info.argtypes = []

    def is_connected(self) -> bool:
        """Verifica se o teclado Wooting está conectado."""
        self._connected = self._sdk.wooting_rgb_kbd_connected()
        return self._connected

    def reset(self) -> bool:
        """Restaura as cores originais do teclado."""
        return self._sdk.wooting_rgb_reset_rgb()

    def close(self) -> bool:
        """Reseta as cores e fecha a conexão com o teclado."""
        try:
            self._sdk.wooting_rgb_reset_rgb()
        except Exception:
            pass
        try:
            result = self._sdk.wooting_rgb_close()
        except Exception:
            result = False
        self._connected = False
        return result

    def __del__(self):
        """Fallback: tenta libertar o SDK se o objecto for garbage-collected."""
        try:
            if self._connected:
                self._sdk.wooting_rgb_reset_rgb()
                self._sdk.wooting_rgb_close()
                self._connected = False
        except Exception:
            pass

    def set_key(self, row: int, col: int, r: int, g: int, b: int) -> bool:
        """Define a cor de uma tecla diretamente (atualiza imediatamente)."""
        return self._sdk.wooting_rgb_direct_set_key(row, col, r, g, b)

    def reset_key(self, row: int, col: int) -> bool:
        """Reseta uma tecla para a cor original."""
        return self._sdk.wooting_rgb_direct_reset_key(row, col)

    def array_set_single(self, row: int, col: int, r: int, g: int, b: int) -> bool:
        """Define a cor de uma tecla no buffer (precisa chamar update_keyboard)."""
        return self._sdk.wooting_rgb_array_set_single(row, col, r, g, b)

    def array_update(self) -> bool:
        """Envia o buffer de cores para o teclado."""
        return self._sdk.wooting_rgb_array_update_keyboard()

    def array_auto_update(self, enabled: bool):
        """Habilita/desabilita atualização automática após cada set_single."""
        self._sdk.wooting_rgb_array_auto_update(enabled)

    def set_full_color(self, r: int, g: int, b: int) -> bool:
        """Define todas as teclas com a mesma cor."""
        buffer_size = WOOTING_RGB_ROWS * WOOTING_RGB_COLS * 3
        colors = (c_uint8 * buffer_size)()
        for i in range(0, buffer_size, 3):
            colors[i] = r
            colors[i + 1] = g
            colors[i + 2] = b
        result = self._sdk.wooting_rgb_array_set_full(colors)
        if result:
            self._sdk.wooting_rgb_array_update_keyboard()
        return result

    def set_full_matrix(self, matrix: list) -> bool:
        """
        Define as cores de todo o teclado usando uma matriz.
        matrix: lista de listas [row][col] = (r, g, b)
        """
        buffer_size = WOOTING_RGB_ROWS * WOOTING_RGB_COLS * 3
        colors = (c_uint8 * buffer_size)()
        idx = 0
        for row in range(WOOTING_RGB_ROWS):
            for col in range(WOOTING_RGB_COLS):
                if row < len(matrix) and col < len(matrix[row]):
                    r, g, b = matrix[row][col]
                else:
                    r, g, b = 0, 0, 0
                colors[idx] = r
                colors[idx + 1] = g
                colors[idx + 2] = b
                idx += 3
        result = self._sdk.wooting_rgb_array_set_full(colors)
        if result:
            self._sdk.wooting_rgb_array_update_keyboard()
        return result

    def get_device_info(self):
        """Retorna informações sobre o dispositivo conectado."""
        device_types = {1: "Keyboard TKL", 2: "Keyboard Full", 3: "Keyboard 60%",
                        4: "Keypad 3KL", 5: "Keyboard 80%"}
        layouts = {-1: "Unknown", 0: "ANSI", 1: "ISO", 2: "JIS",
                   3: "ANSI Split", 4: "ISO Split"}
        info_ptr = self._sdk.wooting_rgb_device_info()
        if info_ptr:
            info = info_ptr.contents
            return {
                "connected": info.connected,
                "model": info.model.decode("utf-8") if info.model else "Unknown",
                "max_rows": info.max_rows,
                "max_columns": info.max_columns,
                "led_index_max": info.led_index_max,
                "device_type": device_types.get(info.device_type, f"Unknown({info.device_type})"),
                "v2_interface": info.v2_interface,
                "layout": layouts.get(info.layout, f"Unknown({info.layout})"),
                "uses_small_packets": info.uses_small_packets,
                "uses_multi_report": info.uses_multi_report,
            }
        return None

    def set_row_color(self, row: int, r: int, g: int, b: int):
        """Define todas as teclas de uma linha com a mesma cor."""
        for col in range(WOOTING_RGB_COLS):
            self.array_set_single(row, col, r, g, b)
        self.array_update()

    def gradient_horizontal(self, color_start: tuple, color_end: tuple):
        """Aplica um gradiente horizontal no teclado."""
        r1, g1, b1 = color_start
        r2, g2, b2 = color_end
        for col in range(WOOTING_RGB_COLS):
            t = col / max(WOOTING_RGB_COLS - 1, 1)
            r = int(r1 + (r2 - r1) * t)
            g = int(g1 + (g2 - g1) * t)
            b = int(b1 + (b2 - b1) * t)
            for row in range(WOOTING_RGB_ROWS):
                self.array_set_single(row, col, r, g, b)
        self.array_update()

    def gradient_vertical(self, color_start: tuple, color_end: tuple):
        """Aplica um gradiente vertical no teclado."""
        r1, g1, b1 = color_start
        r2, g2, b2 = color_end
        for row in range(WOOTING_RGB_ROWS):
            t = row / max(WOOTING_RGB_ROWS - 1, 1)
            r = int(r1 + (r2 - r1) * t)
            g = int(g1 + (g2 - g1) * t)
            b = int(b1 + (b2 - b1) * t)
            for col in range(WOOTING_RGB_COLS):
                self.array_set_single(row, col, r, g, b)
        self.array_update()
