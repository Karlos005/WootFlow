"""
Integração do Screen Ambience com o sistema de perfis RGB.
Permite usar Screen Ambience como um perfil ativo no sistema principal.
"""

import json
import os
from collections import defaultdict
from typing import Optional, Dict, Any, Iterable, List, Tuple
from utils.wooting_rgb import WootFlowRGB, WOOTING_RGB_ROWS, WOOTING_RGB_COLS
from core.effects_engine import ALL_KEYS
from core.screen_ambience import (
    ScreenAmbienceEngine, 
    ScreenAmbienceConfig
)


# Mapa de teclas (mesmo do game_profiles.py para consistência)
KEY_MAP = {
    "ESC": (1, 0), "1": (1, 1), "2": (1, 2), "3": (1, 3), "4": (1, 4),
    "5": (1, 5), "6": (1, 6), "7": (1, 7), "8": (1, 8), "9": (1, 9),
    "0": (1, 10), "-": (1, 11), "=": (1, 12), "BACKSPACE": (1, 13),

    "TAB": (2, 0), "Q": (2, 1), "W": (2, 2), "E": (2, 3), "R": (2, 4),
    "T": (2, 5), "Y": (2, 6), "U": (2, 7), "I": (2, 8), "O": (2, 9),
    "P": (2, 10), "[": (2, 11), "]": (2, 12),

    "CAPS": (3, 0), "A": (3, 1), "S": (3, 2), "D": (3, 3), "F": (3, 4),
    "G": (3, 5), "H": (3, 6), "J": (3, 7), "K": (3, 8), "L": (3, 9),
    ";": (3, 10), "'": (3, 11), "~": (3, 12), "ENTER": (3, 13),

    "LSHIFT": (4, 0), "<": (4, 1), "Z": (4, 2), "X": (4, 3), "C": (4, 4),
    "V": (4, 5), "B": (4, 6), "N": (4, 7), "M": (4, 8), ",": (4, 9),
    ".": (4, 10), "/": (4, 11), "RSHIFT": (4, 13),

    "LCTRL": (5, 0), "LWIN": (5, 1), "LALT": (5, 2), "SPACE": (5, 6),
    "RALT": (5, 10), "MENU": (5, 11), "RCTRL": (5, 12), "FN": (5, 13),
}

COORD_TO_KEY = {coords: key for key, coords in KEY_MAP.items()}

# Geometria visual do 60HE ISO PT, alinhada com o preview do frontend.
LED_LAYOUT = {
    (1, 0): (0.0, 1.0), (1, 1): (1.0, 1.0), (1, 2): (2.0, 1.0), (1, 3): (3.0, 1.0),
    (1, 4): (4.0, 1.0), (1, 5): (5.0, 1.0), (1, 6): (6.0, 1.0), (1, 7): (7.0, 1.0),
    (1, 8): (8.0, 1.0), (1, 9): (9.0, 1.0), (1, 10): (10.0, 1.0), (1, 11): (11.0, 1.0),
    (1, 12): (12.0, 1.0), (1, 13): (13.0, 2.0),
    (2, 0): (0.0, 1.5), (2, 1): (1.5, 1.0), (2, 2): (2.5, 1.0), (2, 3): (3.5, 1.0),
    (2, 4): (4.5, 1.0), (2, 5): (5.5, 1.0), (2, 6): (6.5, 1.0), (2, 7): (7.5, 1.0),
    (2, 8): (8.5, 1.0), (2, 9): (9.5, 1.0), (2, 10): (10.5, 1.0), (2, 11): (11.5, 1.0),
    (2, 12): (12.5, 1.0),
    (3, 0): (0.0, 1.75), (3, 1): (1.75, 1.0), (3, 2): (2.75, 1.0), (3, 3): (3.75, 1.0),
    (3, 4): (4.75, 1.0), (3, 5): (5.75, 1.0), (3, 6): (6.75, 1.0), (3, 7): (7.75, 1.0),
    (3, 8): (8.75, 1.0), (3, 9): (9.75, 1.0), (3, 10): (10.75, 1.0), (3, 11): (11.75, 1.0),
    (3, 12): (12.75, 1.0), (3, 13): (13.75, 1.25),
    (4, 0): (0.0, 1.25), (4, 1): (1.25, 1.0), (4, 2): (2.25, 1.0), (4, 3): (3.25, 1.0),
    (4, 4): (4.25, 1.0), (4, 5): (5.25, 1.0), (4, 6): (6.25, 1.0), (4, 7): (7.25, 1.0),
    (4, 8): (8.25, 1.0), (4, 9): (9.25, 1.0), (4, 10): (10.25, 1.0), (4, 11): (11.25, 1.0),
    (4, 13): (12.25, 2.75),
    # A barra de espaço tem 5 LEDs (colunas 4..8) de 1,25 cada, como no preview e na Wootility.
    (5, 0): (0.0, 1.25), (5, 1): (1.25, 1.25), (5, 2): (2.5, 1.25),
    (5, 4): (3.75, 1.25), (5, 5): (5.0, 1.25), (5, 6): (6.25, 1.25),
    (5, 7): (7.5, 1.25), (5, 8): (8.75, 1.25),
    (5, 10): (10.0, 1.25), (5, 11): (11.25, 1.25),
    (5, 12): (12.5, 1.25), (5, 13): (13.75, 1.25),
}

KEYBOARD_WIDTH_UNITS = 15.0
KEYBOARD_HEIGHT_UNITS = 5.0
ROW_SAMPLE_HEIGHT_UNITS = 0.72


class ScreenAmbienceProfile:
    """Gerenciador do perfil Screen Ambience para WootFlow."""
    
    def __init__(self, kb: WootFlowRGB, profile_data: Dict[str, Any]):
        """
        Inicializa o perfil Screen Ambience.
        
        Args:
            kb: Instância WootFlowRGB conectada
            profile_data: Dados do perfil (JSON)
        """
        self.kb = kb
        self.profile_data = profile_data
        self.engine: Optional[ScreenAmbienceEngine] = None
        self.is_active = False
        
        # Config
        self.config = self._build_config()
        
        # Mapeamento regiões -> teclas
        self.region_keys = self._build_region_map()
        self.led_brightness = self._build_led_brightness_map()
        self.individual_brightness = self._build_individual_brightness_config()
        self.led_sample_regions = self._build_led_sample_regions()
        
        print("[Screen Ambience] Perfil inicializado")

    def _build_individual_brightness_config(self) -> Dict[str, float | bool]:
        """Configura resposta de brilho individual por LED baseada na luminância local."""
        cfg = self.profile_data.get("individual_brightness", {}) or {}

        enabled = bool(cfg.get("enabled", True))
        try:
            min_scale = float(cfg.get("min_scale", 0.35))
        except Exception:
            min_scale = 0.35
        try:
            max_scale = float(cfg.get("max_scale", 1.8))
        except Exception:
            max_scale = 1.8
        try:
            gamma = float(cfg.get("gamma", 0.75))
        except Exception:
            gamma = 0.75

        min_scale = max(0.05, min(2.0, min_scale))
        max_scale = max(min_scale, min(3.0, max_scale))
        gamma = max(0.25, min(2.5, gamma))

        return {
            "enabled": enabled,
            "min_scale": min_scale,
            "max_scale": max_scale,
            "gamma": gamma,
        }

    def _apply_individual_brightness(self, color: Tuple[int, int, int]) -> Tuple[int, int, int]:
        """Aplica curva de brilho local por LED para reforçar hotspots do ecrã."""
        cfg = self.individual_brightness
        if not cfg.get("enabled", True):
            return color

        r, g, b = color
        luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0

        min_scale = float(cfg["min_scale"])
        max_scale = float(cfg["max_scale"])
        gamma = float(cfg["gamma"])

        scale = min_scale + (luminance ** gamma) * (max_scale - min_scale)
        r = max(0, min(255, int(r * scale)))
        g = max(0, min(255, int(g * scale)))
        b = max(0, min(255, int(b * scale)))
        return (r, g, b)

    def _build_led_brightness_map(self) -> Dict[Tuple[int, int], float]:
        """Constrói multiplicador de brilho por LED com base na região da grid."""
        per_region = self.profile_data.get("region_brightness", {}) or {}
        brightness_map: Dict[Tuple[int, int], float] = {}

        for region, keys in self.region_keys.items():
            factor_raw = per_region.get(str(region), per_region.get(region, 1.0))
            try:
                factor = float(factor_raw)
            except Exception:
                factor = 1.0
            factor = max(0.1, min(2.0, factor))
            for coords in keys:
                brightness_map[coords] = factor

        return brightness_map
    
    def _build_config(self) -> ScreenAmbienceConfig:
        """Constrói ScreenAmbienceConfig a partir do JSON do perfil."""
        return ScreenAmbienceConfig(
            mode=self.profile_data.get("mode", "cinematic"),
            fps=self.profile_data.get("fps", 60),
            grid_size=self.profile_data.get("grid_size", 3),
            brightness=self.profile_data.get("brightness", 1.0),
            color_sensitivity=self.profile_data.get("color_sensitivity", "medium"),
            smoothing_factor=self.profile_data.get("smoothing_factor", 0.7),
            exclude_black=self.profile_data.get("exclude_black", True),
            exclude_white=self.profile_data.get("exclude_white", False),
            black_threshold=self.profile_data.get("black_threshold", 30),
            white_threshold=self.profile_data.get("white_threshold", 220),
            monitor_index=self.profile_data.get("monitor_index", 0),
        )
    
    def _build_region_map(self) -> Dict[int, list]:
        """Constrói mapeamento de região -> LEDs físicos."""
        region_map: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
        assigned = set()

        for zone in self.profile_data.get("zones", []):
            region = zone.get("region")
            keys = zone.get("keys", [])
            if region is None:
                continue

            for key in keys:
                coords = KEY_MAP.get(key)
                if coords is None or coords in assigned:
                    continue
                region_map[region].append(coords)
                assigned.add(coords)

        for region, coords in self._build_auto_region_map(excluded=assigned).items():
            region_map[region].extend(coords)

        return dict(region_map)

    def _build_auto_region_map(self, excluded: Iterable[Tuple[int, int]]) -> Dict[int, List[Tuple[int, int]]]:
        """Distribui LEDs não mapeados pelas regiões da grid do Screen Ambience."""
        excluded_coords = set(excluded)
        auto_map: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
        max_row = max(row for row, _ in ALL_KEYS)
        max_col = max(col for _, col in ALL_KEYS)

        for row, col in ALL_KEYS:
            coords = (row, col)
            if coords in excluded_coords:
                continue

            normalized_row = (row - 1) / max(1, max_row - 1)
            normalized_col = col / max(1, max_col)
            grid_row = min(self.config.grid_size - 1, int(normalized_row * self.config.grid_size))
            grid_col = min(self.config.grid_size - 1, int(normalized_col * self.config.grid_size))
            region = grid_row * self.config.grid_size + grid_col
            auto_map[region].append(coords)

        return auto_map
    
    def activate(self):
        """Ativa o perfil Screen Ambience."""
        if self.is_active:
            return
        print("[Screen Ambience] Ativando perfil...")
        # Criar engine
        self.engine = ScreenAmbienceEngine(self.config)
        self.engine.set_sample_regions(self.led_sample_regions)
        # Definir callback para atualizar LEDs
        self.engine.set_on_colors_updated(self._on_colors_updated)
        # Iniciar engine
        self.engine.start()
        self.is_active = True
        # Forçar atualização imediata do frame
        if hasattr(self.engine, 'on_colors_updated') and self.engine.on_colors_updated:
            # Gera um frame inicial para garantir atualização
            if self.engine.sample_regions:
                frame = self.engine.capture.capture_frame()
                if frame is not None:
                    raw_colors = self.engine.analyzer.analyze_regions(frame, self.engine.sample_regions)
                    smoothed_colors = {
                        sample_id: self.engine.smoother.smooth(sample_id, color)
                        for sample_id, color in raw_colors.items()
                    }
                    self.engine.on_colors_updated(smoothed_colors)
        print(f"[Screen Ambience] Perfil ativo - Modo: {self.config.mode}")
    
    def deactivate(self):
        """Desativa o perfil Screen Ambience."""
        if not self.is_active:
            return
        
        print("[Screen Ambience] Desativando perfil...")
        
        if self.engine:
            self.engine.stop()
        
        self.is_active = False
        
        # Apagar LEDs
        self._clear_leds()
    
    def _on_colors_updated(self, colors):
        """
        Callback acionado quando cores são atualizadas.
        Atualiza LEDs do teclado com as novas cores.
        
        Args:
            colors: Lista de cores RGB (região por região)
        """
        try:
            if isinstance(colors, dict):
                for coords, color in colors.items():
                    self._set_led_color(coords, color)
                self._commit_keyboard_buffer()
                return

            for region_id, color in enumerate(colors):
                if region_id in self.region_keys:
                    keys = self.region_keys[region_id]
                    self._set_region_color(keys, color)
            
            # Atualizar hardware (compatível com wrappers/SDKs diferentes)
            self._commit_keyboard_buffer()
        except Exception as e:
            print(f"[Screen Ambience] Erro ao atualizar LEDs: {e}")

    def _commit_keyboard_buffer(self):
        """Envia o buffer RGB para o hardware com fallback de compatibilidade."""
        if hasattr(self.kb, "array_update"):
            self.kb.array_update()
            return
        if hasattr(self.kb, "array_flush"):
            self.kb.array_flush()
            return
        raise AttributeError("Keyboard object does not expose array_update/array_flush")
    
    def _set_region_color(self, keys: list, color: tuple):
        """Define cor para um grupo de LEDs físicos."""
        for row, col in keys:
            self._set_led_color((row, col), color)

    def _set_led_color(self, coords: Tuple[int, int], color: tuple):
        """Define cor para um LED físico individual."""
        row, col = coords
        r, g, b = color
        r, g, b = self._apply_individual_brightness((r, g, b))
        factor = self.led_brightness.get(coords, 1.0)
        r = max(0, min(255, int(r * factor)))
        g = max(0, min(255, int(g * factor)))
        b = max(0, min(255, int(b * factor)))
        try:
            self.kb.array_set_single(row, col, r, g, b)
        except Exception as e:
            key_name = COORD_TO_KEY.get((row, col), f"({row}, {col})")
            print(f"[Screen Ambience] Erro ao definir cor da tecla {key_name}: {e}")

    def _build_led_sample_regions(self) -> Dict[Tuple[int, int], Tuple[float, float, float, float]]:
        """Cria regiões normalizadas de amostragem por LED, no estilo canvas do SignalRGB."""
        sample_regions: Dict[Tuple[int, int], Tuple[float, float, float, float]] = {}
        sample_area_scale = max(0.2, min(1.2, self.config.sample_area_scale))
        sample_height = (ROW_SAMPLE_HEIGHT_UNITS / KEYBOARD_HEIGHT_UNITS) * sample_area_scale

        for coords, (x, width) in LED_LAYOUT.items():
            center_x = (x + (width / 2)) / KEYBOARD_WIDTH_UNITS
            center_y = ((coords[0] - 1) + 0.5) / KEYBOARD_HEIGHT_UNITS
            sample_width = (width / KEYBOARD_WIDTH_UNITS) * sample_area_scale
            sample_regions[coords] = (
                max(0.0, min(1.0, center_x)),
                max(0.0, min(1.0, center_y)),
                min(1.0, sample_width),
                min(1.0, sample_height),
            )

        return sample_regions
    
    def _clear_leds(self):
        """Apaga todos os LEDs."""
        try:
            for row in range(WOOTING_RGB_ROWS):
                for col in range(WOOTING_RGB_COLS):
                    self.kb.array_set_single(row, col, 0, 0, 0)
            self._commit_keyboard_buffer()
        except Exception as e:
            print(f"[Screen Ambience] Erro ao apagar LEDs: {e}")
    
    def set_mode(self, mode: str):
        """Muda o modo (cinematic, dynamic, gaming)."""
        if mode not in ["cinematic", "dynamic", "gaming"]:
            print(f"[Screen Ambience] Modo desconhecido: {mode}")
            return
        
        was_active = self.is_active
        if was_active:
            self.deactivate()
        
        # Aplicar preset de modo
        preset = self.profile_data.get("presets", {}).get(mode)
        if preset:
            self.config.mode = mode
            self.config.fps = preset.get("fps", self.config.fps)
            self.config.smoothing_factor = preset.get("smoothing_factor", self.config.smoothing_factor)
            self.config.color_sensitivity = preset.get("color_sensitivity", self.config.color_sensitivity)
            self.config.brightness = preset.get("brightness", self.config.brightness)
        
        if was_active:
            self.activate()
        
        print(f"[Screen Ambience] Modo alterado para: {mode}")
    
    def set_brightness(self, brightness: float):
        """Altera brilho global."""
        self.config.brightness = max(0.0, min(2.0, brightness))
        print(f"[Screen Ambience] Brilho: {self.config.brightness:.1f}")
    
    def set_fps(self, fps: int):
        """Altera FPS."""
        self.config.fps = max(30, min(120, fps))
        
        if self.is_active and self.engine:
            self.engine.config.fps = self.config.fps
        
        print(f"[Screen Ambience] FPS: {self.config.fps}")
    
    def get_stats(self) -> Dict:
        """Retorna estatísticas do engine."""
        if not self.engine:
            return {"status": "inactive"}
        
        return {
            "status": "active",
            **self.engine.get_stats()
        }
    
    def print_status(self):
        """Exibe status atual."""
        stats = self.get_stats()
        print("\n" + "=" * 50)
        print("  Screen Ambience - Status")
        print("=" * 50)
        print(f"  Status: {stats.get('status', 'unknown')}")
        if stats.get('actual_fps'):
            print(f"  FPS: {stats['actual_fps']:.1f}")
            print(f"  Frame time: {stats['avg_frame_time_ms']:.2f}ms")
        print(f"  Modo: {self.config.mode}")
        print(f"  Grid: {self.config.grid_size}x{self.config.grid_size}")
        print(f"  Brilho: {self.config.brightness:.1f}")
        print(f"  Suavização: {self.config.smoothing_factor:.1f}")
        print("=" * 50 + "\n")


def load_ambience_profile(kb: WootFlowRGB, profile_dir: str = "profiles") -> ScreenAmbienceProfile:
    """
    Carrega e inicializa o perfil Screen Ambience.
    
    Args:
        kb: Instância WootFlowRGB
        profile_dir: Diretório de perfis
    
    Returns:
        ScreenAmbienceProfile inicializado
    """
    profile_path = os.path.join(profile_dir, "screen_ambience.json")
    
    if not os.path.exists(profile_path):
        raise FileNotFoundError(f"Perfil Screen Ambience não encontrado: {profile_path}")
    
    with open(profile_path, "r", encoding="utf-8") as f:
        profile_data = json.load(f)
    
    return ScreenAmbienceProfile(kb, profile_data)
