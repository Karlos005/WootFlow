"""Efeito que mostra no teclado as barras do HUD lidas do ecrã (vida, escudo, munição...)."""
import math

import core.effects_engine as engine
from core.effects_engine import Effect, lerp_color, scale_color
from core.hud_tracker import TRACKER

STALE_SECONDS = 2.0   # sem leituras novas durante este tempo = HUD não está a ser lido
TRACK_LEVEL = 0.10    # brilho do "trilho" das teclas ainda vazias


class HudMetersEffect(Effect):
    """Cada medidor enche uma linha do teclado, da esquerda para a direita."""
    name = "HUD do jogo"

    def __init__(self):
        super().__init__()
        self.color1 = (0, 60, 80)  # cor de fundo suave quando não há leitura

    def _row_cells(self, row: int) -> list:
        return sorted((r, c) for r, c in engine.ALL_KEYS if r == row)

    def update(self, kb, t: float):
        meters = TRACKER.meters()
        readings = TRACKER.snapshot(t)
        bg = scale_color(self.color1, 0.25 * self.brightness)
        for row, col in engine.ALL_KEYS:
            kb.array_set_single(row, col, *bg)

        for meter in meters:
            reading = readings.get(meter.id)
            cells = self._row_cells(meter.row)
            if not cells:
                continue
            if reading is None or reading["age"] > STALE_SECONDS:
                for row, col in cells:
                    kb.array_set_single(row, col, 0, 0, 0)
                continue

            fraction = reading["fraction"]
            base = lerp_color(meter.color_empty, meter.color_full, fraction)
            pulse = 1.0
            if fraction <= meter.low_threshold:
                pulse = 0.55 + 0.45 * math.sin(t * 8.0)   # vida baixa: a barra pulsa
            filled = fraction * len(cells)
            for i, (row, col) in enumerate(cells):
                level = max(0.0, min(1.0, filled - i))   # a última tecla enche parcialmente
                intensity = TRACK_LEVEL + (1.0 - TRACK_LEVEL) * level * pulse
                color = scale_color(base, intensity * self.brightness)
                if reading["flash"] > 0:   # dano: a barra pisca a branco e desvanece
                    color = lerp_color(color, (255, 255, 255), reading["flash"] * 0.85)
                kb.array_set_single(row, col, *color)
        kb.array_update()
