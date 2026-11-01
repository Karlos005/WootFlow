"""
Motor de efeitos avançados para teclado Wooting.
Efeitos dinâmicos frame-by-frame: wave, ripple, reactive typing,
equalizer, starfield, fire, matrix rain, aurora, gradient, etc.
"""

import math
import time
import random
import threading
from utils.wooting_rgb import WootFlowRGB, WOOTING_RGB_ROWS
from core.devices import KeyboardProfile, default_profile


# ============================================================================
# Utilidades de cor
# ============================================================================

def hsv_to_rgb(h: float, s: float = 1.0, v: float = 1.0) -> tuple[int, int, int]:
    """HSV (h=0-360, s=0-1, v=0-1) → RGB (0-255)."""
    h = h % 360
    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c
    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    return (int((r + m) * 255), int((g + m) * 255), int((b + m) * 255))


def lerp_color(c1: tuple, c2: tuple, t: float) -> tuple[int, int, int]:
    """Interpolação linear entre duas cores."""
    t = max(0.0, min(1.0, t))
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def scale_color(color: tuple, factor: float) -> tuple[int, int, int]:
    """Escala a intensidade de uma cor."""
    return (
        min(255, int(color[0] * factor)),
        min(255, int(color[1] * factor)),
        min(255, int(color[2] * factor)),
    )


# ============================================================================
# Layouts de teclas físicas do 60HE (para efeitos que precisam de posição)
# ============================================================================
# Mapa de teclas ativas (row, col) - posições reais no Wooting 60HE ISO
# O SDK usa uma matrix 6x21. Para o 60HE (sem row de F-keys):
#   - Row 0 do SDK = F-keys (não existe no 60HE)
#   - Row 1 = Number row (ESC, 1-0, -, =, Backspace)
#   - Row 2 = Tab row (Tab, Q-P, +, ´)
#   - Row 3 = Home row (Caps, A-L, ;, ', #, Enter)
#   - Row 4 = Shift row (LShift, ISO<, Z-/, RShift)
#   - Row 5 = Bottom row (LCtrl, Win, Alt, Space LEDs centrais, AltGr, Menu, RCtrl, Fn)
PHYSICAL_KEYS_60HE = [
    # Row 1 (SDK): ESC, 1-0, ', «, BACKSPACE
    [(1, 0), (1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (1, 8), (1, 9), (1, 10), (1, 11), (1, 12), (1, 13)],
    # Row 2 (SDK): TAB, Q-P, +, ´
    [(2, 0), (2, 1), (2, 2), (2, 3), (2, 4), (2, 5), (2, 6), (2, 7), (2, 8), (2, 9), (2, 10), (2, 11), (2, 12)],
    # Row 3 (SDK): CAPS, A-L, Ç, º, ~, ENTER
    [(3, 0), (3, 1), (3, 2), (3, 3), (3, 4), (3, 5), (3, 6), (3, 7), (3, 8), (3, 9), (3, 10), (3, 11), (3, 12), (3, 13)],
    # Row 4 (SDK): LSHIFT, ISO<, Z-/, RSHIFT  (col 12 = NOLED)
    [(4, 0), (4, 1), (4, 2), (4, 3), (4, 4), (4, 5), (4, 6), (4, 7), (4, 8), (4, 9), (4, 10), (4, 11), (4, 13)],
    # Row 5 (SDK): LCTRL, LWIN, LALT, SPACE LEDs (4-8), ALTGR, MENU, RCTRL, FN
    [(5, 0), (5, 1), (5, 2), (5, 4), (5, 5), (5, 6), (5, 7), (5, 8), (5, 10), (5, 11), (5, 12), (5, 13)],
]

ALL_KEYS = [(r, c) for row in PHYSICAL_KEYS_60HE for r, c in row]
ALL_KEYS_SET = set(ALL_KEYS)

# Colunas com LED no layout ativo (14 no 60HE). Atualizado por apply_profile().
LAYOUT_COLS = 14
ACTIVE_PROFILE: KeyboardProfile = default_profile()


def apply_profile(profile: KeyboardProfile):
    """Adapta os mapas de teclas ao teclado detetado.

    Altera as listas/dicts no lugar para que os módulos que já os importaram
    (server.py) vejam o novo layout. Efeitos criados depois lêem LAYOUT_COLS.
    """
    global LAYOUT_COLS, ACTIVE_PROFILE
    ACTIVE_PROFILE = profile
    PHYSICAL_KEYS_60HE[:] = [list(row) for row in profile.keys]
    ALL_KEYS[:] = [(r, c) for row in PHYSICAL_KEYS_60HE for r, c in row]
    ALL_KEYS_SET.clear()
    ALL_KEYS_SET.update(ALL_KEYS)
    LAYOUT_COLS = max(1, max((c for _, c in ALL_KEYS), default=13) + 1)
    _rebuild_eq_columns()


# ============================================================================
# Classe base de efeito
# ============================================================================

class Effect:
    """Base para todos os efeitos."""
    name = "Base"

    def __init__(self):
        self.speed = 1.0
        self.brightness = 1.0
        self.color1 = (0, 200, 200)
        self.color2 = (128, 0, 255)

    def update(self, kb: WootFlowRGB, t: float):
        """Atualiza o efeito num frame. t = time.time()."""
        pass


# ============================================================================
# Efeitos implementados
# ============================================================================

class RainbowWaveEffect(Effect):
    """Onda arco-íris horizontal que percorre o teclado."""
    name = "Rainbow Wave"

    def __init__(self):
        super().__init__()
        self.speed = 60.0   # graus por segundo
        self.spread = 20.0  # graus entre colunas

    def update(self, kb: WootFlowRGB, t: float):
        offset = t * self.speed
        for row, col in ALL_KEYS:
            hue = (offset + col * self.spread + row * 8) % 360
            r, g, b = hsv_to_rgb(hue, 1.0, self.brightness)
            kb.array_set_single(row, col, r, g, b)
        kb.array_update()


class ColorWaveEffect(Effect):
    """Onda de duas cores que percorre o teclado."""
    name = "Color Wave"

    def __init__(self):
        super().__init__()
        self.speed = 2.0
        self.color1 = (0, 200, 200)
        self.color2 = (128, 0, 255)

    def update(self, kb: WootFlowRGB, t: float):
        for row, col in ALL_KEYS:
            wave = (math.sin(t * self.speed + col * 0.5 + row * 0.3) + 1) / 2
            r, g, b = lerp_color(self.color1, self.color2, wave)
            r = min(255, int(r * self.brightness))
            g = min(255, int(g * self.brightness))
            b = min(255, int(b * self.brightness))
            kb.array_set_single(row, col, r, g, b)
        kb.array_update()


class BreathingEffect(Effect):
    """Respiração suave - pulsa entre duas intensidades."""
    name = "Breathing"

    def __init__(self):
        super().__init__()
        self.speed = 1.0
        self.color1 = (0, 200, 200)
        self.min_brightness = 0.1

    def update(self, kb: WootFlowRGB, t: float):
        pulse = (math.sin(t * self.speed * math.pi) + 1) / 2
        intensity = self.min_brightness + pulse * (self.brightness - self.min_brightness)
        r = min(255, int(self.color1[0] * intensity))
        g = min(255, int(self.color1[1] * intensity))
        b = min(255, int(self.color1[2] * intensity))
        for row, col in ALL_KEYS:
            kb.array_set_single(row, col, r, g, b)
        kb.array_update()


class SpectrumCycleEffect(Effect):
    """Ciclo de espectro - todas as teclas mudam de cor juntas."""
    name = "Spectrum Cycle"

    def __init__(self):
        super().__init__()
        self.speed = 30.0  # graus por segundo

    def update(self, kb: WootFlowRGB, t: float):
        hue = (t * self.speed) % 360
        r, g, b = hsv_to_rgb(hue, 1.0, self.brightness)
        for row, col in ALL_KEYS:
            kb.array_set_single(row, col, r, g, b)
        kb.array_update()


class RippleEffect(Effect):
    """Efeito ripple - ondas expandem de teclas pressionadas."""
    name = "Ripple"

    def __init__(self):
        super().__init__()
        self.color1 = (0, 255, 200)
        self.speed = 8.0
        self.max_radius = 10.0
        self.fade_speed = 3.0
        self._ripples = []  # [(center_row, center_col, start_time)]
        self._lock = threading.Lock()
        self._bg = (5, 5, 15)

    def trigger(self, row: int, col: int):
        """Adiciona um ripple numa posição."""
        with self._lock:
            self._ripples.append((row, col, time.time()))
            # Limitar a 20 ripples simultâneos
            if len(self._ripples) > 20:
                self._ripples = self._ripples[-20:]

    def update(self, kb: WootFlowRGB, t: float):
        # Base escura
        for row, col in ALL_KEYS:
            kb.array_set_single(row, col, *self._bg)

        with self._lock:
            active = []
            for cr, cc, st in self._ripples:
                age = t - st
                if age < self.max_radius / self.speed + 1.0:
                    active.append((cr, cc, st))
            self._ripples = active

            # Aplicar cada ripple
            for row, col in ALL_KEYS:
                max_intensity = 0.0
                for cr, cc, st in active:
                    age = t - st
                    radius = age * self.speed
                    dist = math.sqrt((row - cr) ** 2 + (col - cc) ** 2)
                    ring_dist = abs(dist - radius)
                    if ring_dist < 1.5:
                        fade = max(0, 1.0 - age * self.fade_speed / self.max_radius)
                        intensity = (1.0 - ring_dist / 1.5) * fade
                        max_intensity = max(max_intensity, intensity)

                if max_intensity > 0:
                    r, g, b = scale_color(self.color1, max_intensity * self.brightness)
                    kb.array_set_single(row, col, r, g, b)

        kb.array_update()


class ReactiveTypingEffect(Effect):
    """Teclas acendem quando pressionadas e desvanecem."""
    name = "Reactive Typing"

    def __init__(self):
        super().__init__()
        self.color1 = (0, 255, 200)
        self.fade_time = 0.8  # segundos para desaparecer
        self._key_times = {}  # {(row,col): last_press_time}
        self._lock = threading.Lock()
        self._bg = (5, 5, 10)

    def trigger(self, row: int, col: int):
        """Regista que uma tecla foi pressionada."""
        with self._lock:
            self._key_times[(row, col)] = time.time()

    def update(self, kb: WootFlowRGB, t: float):
        with self._lock:
            keys = dict(self._key_times)

        for row, col in ALL_KEYS:
            press_t = keys.get((row, col))
            if press_t and t - press_t < self.fade_time:
                fade = 1.0 - (t - press_t) / self.fade_time
                r, g, b = scale_color(self.color1, fade * self.brightness)
                kb.array_set_single(row, col, r, g, b)
            else:
                kb.array_set_single(row, col, *self._bg)

        kb.array_update()


class FireEffect(Effect):
    """Efeito de fogo - chamas a subir do fundo."""
    name = "Fire"

    def __init__(self):
        super().__init__()
        self._heat = [[0.0] * LAYOUT_COLS for _ in range(WOOTING_RGB_ROWS)]

    def update(self, kb: WootFlowRGB, t: float):
        import random
        # Gerar calor na linha de baixo
        for col in range(LAYOUT_COLS):
            self._heat[WOOTING_RGB_ROWS - 1][col] = random.uniform(0.6, 1.0)

        # Propagar para cima com diffusion
        for row in range(WOOTING_RGB_ROWS - 2, -1, -1):
            for col in range(LAYOUT_COLS):
                left = max(0, col - 1)
                right = min(LAYOUT_COLS - 1, col + 1)
                below = row + 1
                avg = (
                    self._heat[below][left]
                    + self._heat[below][col]
                    + self._heat[below][right]
                    + self._heat[below][col]
                ) / 4.0
                self._heat[row][col] = max(0, avg - 0.08 - random.uniform(0, 0.05))

        # Mapear calor para cores (preto → vermelho → amarelo → branco)
        for row, col in ALL_KEYS:
            h = self._heat[row][col] * self.brightness
            if h < 0.33:
                t2 = h / 0.33
                r, g, b = int(200 * t2), 0, 0
            elif h < 0.66:
                t2 = (h - 0.33) / 0.33
                r, g, b = 200, int(150 * t2), 0
            else:
                t2 = (h - 0.66) / 0.34
                r, g, b = 200 + int(55 * t2), 150 + int(105 * t2), int(80 * t2)
            kb.array_set_single(row, col, min(255, r), min(255, g), min(255, b))

        kb.array_update()


class MatrixRainEffect(Effect):
    """Efeito Matrix - chuva de caracteres verdes a cair."""
    name = "Matrix Rain"

    def __init__(self):
        super().__init__()
        self._drops = [0.0] * LAYOUT_COLS  # posição Y de cada gota
        self._speeds = [0.0] * LAYOUT_COLS
        self.color1 = (0, 255, 70)
        self.speed = 1.0
        import random
        for col in range(LAYOUT_COLS):
            self._drops[col] = random.uniform(-3, WOOTING_RGB_ROWS)
            self._speeds[col] = random.uniform(1.5, 4.0)

    def update(self, kb: WootFlowRGB, t: float):
        import random
        dt = 1 / 60  # assume 60fps

        for col in range(LAYOUT_COLS):
            self._drops[col] += self._speeds[col] * dt * self.speed * 3
            if self._drops[col] > WOOTING_RGB_ROWS + 3:
                self._drops[col] = random.uniform(-4, -1)
                self._speeds[col] = random.uniform(1.5, 4.0)

        for row, col in ALL_KEYS:
            dist = self._drops[col] - row
            if 0 <= dist < 1:
                # Head (branco/verde brilhante)
                r, g, b = scale_color((200, 255, 200), self.brightness)
            elif 0 < dist < 5:
                # Trail
                fade = 1.0 - dist / 5.0
                r, g, b = scale_color(self.color1, fade * self.brightness)
            else:
                r, g, b = 0, min(255, int(15 * self.brightness)), 0
            kb.array_set_single(row, col, r, g, b)

        kb.array_update()


class StarfieldEffect(Effect):
    """Efeito starfield - estrelas a cintilar aleatoriamente."""
    name = "Starfield"

    def __init__(self):
        super().__init__()
        import random
        self._stars = {}
        for r, c in ALL_KEYS:
            self._stars[(r, c)] = {
                "phase": random.uniform(0, math.pi * 2),
                "freq": random.uniform(0.5, 3.0),
                "max_bright": random.uniform(0.55, 1.0),
            }
        self.color1 = (180, 200, 255)
        self._bg = (2, 2, 8)

    def update(self, kb: WootFlowRGB, t: float):
        for row, col in ALL_KEYS:
            star = self._stars.get((row, col))
            if star:
                val = (math.sin(t * star["freq"] * self.speed + star["phase"]) + 1) / 2
                val = val * star["max_bright"] * self.brightness
                if val < 0.1:
                    kb.array_set_single(row, col, *self._bg)
                else:
                    r, g, b = scale_color(self.color1, val)
                    kb.array_set_single(row, col, r, g, b)
            else:
                kb.array_set_single(row, col, *self._bg)
        kb.array_update()


class SolidColorEffect(Effect):
    """Cor sólida em todas as teclas."""
    name = "Solid Color"

    def update(self, kb: WootFlowRGB, t: float):
        r, g, b = scale_color(self.color1, self.brightness)
        for row, col in ALL_KEYS:
            kb.array_set_single(row, col, r, g, b)
        kb.array_update()


class GradientEffect(Effect):
    """Gradiente estático horizontal entre duas cores."""
    name = "Gradient"

    def update(self, kb: WootFlowRGB, t: float):
        for row, col in ALL_KEYS:
            pos = col / 13.0
            r, g, b = lerp_color(self.color1, self.color2, pos)
            r, g, b = scale_color((r, g, b), self.brightness)
            kb.array_set_single(row, col, r, g, b)
        kb.array_update()


class AuroraEffect(Effect):
    """Aurora boreal — ondas lentas multicolores."""
    name = "Aurora"

    def __init__(self):
        super().__init__()
        self.speed = 0.4
        self._palette = [
            (0, 200, 100), (0, 255, 150), (20, 180, 255),
            (80, 80, 255), (150, 50, 200), (0, 220, 180),
        ]

    def update(self, kb: WootFlowRGB, t: float):
        n = len(self._palette)
        for row, col in ALL_KEYS:
            phase = t * self.speed + col * 0.25 + row * 0.15
            idx = phase % n
            i0 = int(idx) % n
            i1 = (i0 + 1) % n
            frac = idx - int(idx)
            r, g, b = lerp_color(self._palette[i0], self._palette[i1], frac)
            noise = math.sin(t * 1.3 + col * 0.7 + row * 1.1) * 0.2 + 0.8
            r, g, b = scale_color((r, g, b), self.brightness * max(0.2, noise))
            kb.array_set_single(row, col, r, g, b)
        kb.array_update()


class RaindropEffect(Effect):
    """Gotas de chuva — teclas aleatórias acendem e desvanecem."""
    name = "Raindrop"

    def __init__(self):
        super().__init__()
        self.speed = 1.0
        self._drops = {}  # {(row,col): start_time}
        self._drop_interval = 0.08
        self._last_drop = 0
        self._fade_time = 0.6
        self._bg = (2, 2, 6)

    def update(self, kb: WootFlowRGB, t: float):
        if t - self._last_drop > self._drop_interval / self.speed:
            self._last_drop = t
            key = random.choice(ALL_KEYS)
            self._drops[key] = t

        expired = []
        for key, st in self._drops.items():
            if t - st > self._fade_time:
                expired.append(key)
        for key in expired:
            del self._drops[key]

        for row, col in ALL_KEYS:
            st = self._drops.get((row, col))
            if st:
                age = t - st
                fade = max(0, 1.0 - age / self._fade_time)
                splash = fade ** 0.5
                r, g, b = lerp_color(self.color1, self.color2, 1.0 - fade)
                r, g, b = scale_color((r, g, b), splash * self.brightness)
                kb.array_set_single(row, col, r, g, b)
            else:
                kb.array_set_single(row, col, *self._bg)
        kb.array_update()


class SparkleEffect(Effect):
    """Brilhos aleatórios — sparkle/confetti."""
    name = "Sparkle"

    def __init__(self):
        super().__init__()
        self.speed = 1.0
        self._sparks = {}
        self._spark_rate = 0.04
        self._last_spark = 0
        self._fade = 0.3
        self._bg = (3, 3, 8)

    def update(self, kb: WootFlowRGB, t: float):
        if t - self._last_spark > self._spark_rate / self.speed:
            self._last_spark = t
            for _ in range(random.randint(1, 3)):
                key = random.choice(ALL_KEYS)
                hue = random.uniform(0, 360)
                self._sparks[key] = (t, hsv_to_rgb(hue))

        expired = []
        for key, (st, _) in self._sparks.items():
            if t - st > self._fade:
                expired.append(key)
        for key in expired:
            del self._sparks[key]

        for row, col in ALL_KEYS:
            spark = self._sparks.get((row, col))
            if spark:
                st, color = spark
                fade = max(0, 1.0 - (t - st) / self._fade)
                r, g, b = scale_color(color, fade * self.brightness)
                kb.array_set_single(row, col, r, g, b)
            else:
                kb.array_set_single(row, col, *self._bg)
        kb.array_update()


class HeartbeatEffect(Effect):
    """Pulso de batimento cardíaco — dois pulsos rápidos seguidos de pausa."""
    name = "Heartbeat"

    def __init__(self):
        super().__init__()
        self.speed = 1.0
        self.color1 = (255, 0, 60)

    def update(self, kb: WootFlowRGB, t: float):
        cycle = (t * self.speed) % 1.5
        if cycle < 0.1:
            intensity = cycle / 0.1
        elif cycle < 0.2:
            intensity = 1.0 - (cycle - 0.1) / 0.1
        elif cycle < 0.35:
            intensity = (cycle - 0.2) / 0.15 * 0.7
        elif cycle < 0.5:
            intensity = 0.7 * (1.0 - (cycle - 0.35) / 0.15)
        else:
            intensity = 0.0

        intensity *= self.brightness
        r, g, b = scale_color(self.color1, intensity)
        for row_keys in PHYSICAL_KEYS_60HE:
            for row, col in row_keys:
                kb.array_set_single(row, col, r, g, b)
        kb.array_update()


class LavaEffect(Effect):
    """Lava — bolhas quentes a mover-se lentamente."""
    name = "Lava"

    def __init__(self):
        super().__init__()
        self.speed = 0.5
        self._offsets = {}
        for r, c in ALL_KEYS:
            self._offsets[(r, c)] = (
                random.uniform(0, 100),
                random.uniform(0, 100),
                random.uniform(0, 100),
            )

    def update(self, kb: WootFlowRGB, t: float):
        ts = t * self.speed
        for row, col in ALL_KEYS:
            ox, oy, oz = self._offsets[(row, col)]
            n1 = math.sin(ts * 0.7 + ox + col * 0.3) * 0.5 + 0.5
            n2 = math.sin(ts * 0.5 + oy + row * 0.5) * 0.5 + 0.5
            n3 = math.sin(ts * 0.3 + oz + col * 0.2 + row * 0.4) * 0.5 + 0.5
            heat = (n1 + n2 + n3) / 3.0

            if heat < 0.3:
                r, g, b = int(80 * heat / 0.3), 0, 0
            elif heat < 0.6:
                t2 = (heat - 0.3) / 0.3
                r, g, b = 80 + int(175 * t2), int(60 * t2), 0
            else:
                t2 = (heat - 0.6) / 0.4
                r, g, b = 255, 60 + int(140 * t2), int(40 * t2)

            r, g, b = scale_color((r, g, b), self.brightness)
            kb.array_set_single(row, col, r, g, b)
        kb.array_update()


class OceanEffect(Effect):
    """Ondas de oceano — movimento fluido azul/cyan."""
    name = "Ocean"

    def __init__(self):
        super().__init__()
        self.speed = 1.0

    def update(self, kb: WootFlowRGB, t: float):
        ts = t * self.speed
        for row, col in ALL_KEYS:
            wave1 = math.sin(ts * 0.8 + col * 0.4 + row * 0.2) * 0.5 + 0.5
            wave2 = math.sin(ts * 1.2 + col * 0.3 - row * 0.5) * 0.5 + 0.5
            wave3 = math.sin(ts * 0.5 + col * 0.15 + row * 0.6) * 0.5 + 0.5
            val = (wave1 + wave2 + wave3) / 3.0

            r = int(20 + 55 * val)
            g = int(105 + 140 * val)
            b = int(165 + 90 * val)
            r, g, b = scale_color((r, g, b), self.brightness)
            kb.array_set_single(row, col, r, g, b)
        kb.array_update()


class MagneticKeysEffect(Effect):
    """Teclas ativas puxam cor para teclas vizinhas com campo de influencia."""
    name = "Magnetic Keys"

    def __init__(self):
        super().__init__()
        self.speed = 1.2
        self.influence = 3.0
        self._falloff = 1.5
        self._bg_mix = 0.42
        self._sources = []  # [(row, col, start_time)]
        self._lock = threading.Lock()

    def trigger(self, row: int, col: int):
        with self._lock:
            self._sources.append((row, col, time.time()))
            if len(self._sources) > 28:
                self._sources = self._sources[-28:]

    def _base_color(self, row: int, col: int, t: float) -> tuple[int, int, int]:
        grad = col / 13.0
        wave = (math.sin(t * 0.7 * self.speed + row * 0.5 + col * 0.25) + 1.0) * 0.5
        blend = max(0.0, min(1.0, grad * 0.7 + wave * 0.3))
        return lerp_color(self.color1, self.color2, blend)

    def update(self, kb: WootFlowRGB, t: float):
        with self._lock:
            alive = []
            for sr, sc, st in self._sources:
                if t - st < 1.8:
                    alive.append((sr, sc, st))
            self._sources = alive
            sources = list(alive)

        radius = max(1.2, float(self.influence))

        for row, col in ALL_KEYS:
            base = self._base_color(row, col, t)
            acc_r = base[0] * self._bg_mix
            acc_g = base[1] * self._bg_mix
            acc_b = base[2] * self._bg_mix
            total = self._bg_mix

            for sr, sc, st in sources:
                age = t - st
                dist = math.sqrt((row - sr) ** 2 + (col - sc) ** 2)
                if dist > radius:
                    continue

                life = max(0.0, 1.0 - age / 1.8)
                pull = max(0.0, 1.0 - dist / radius)
                weight = (pull ** self._falloff) * life * (0.7 + 0.6 * self.speed)

                source_base = self._base_color(sr, sc, t - age * 0.3)
                tint = lerp_color(source_base, self.color1, 0.5)
                acc_r += tint[0] * weight
                acc_g += tint[1] * weight
                acc_b += tint[2] * weight
                total += weight

            r = int(acc_r / total)
            g = int(acc_g / total)
            b = int(acc_b / total)
            # Pequeno boost para evitar sensação de "apagado" em brilho máximo.
            if self.brightness > 0.95:
                r, g, b = scale_color((r, g, b), 1.1)
            r, g, b = scale_color((r, g, b), self.brightness)
            kb.array_set_single(row, col, r, g, b)

        kb.array_update()


class LiquidFlowEffect(Effect):
    """Gradiente fluido animado que deforma em torno das teclas pressionadas."""
    name = "Liquid Flow"

    def __init__(self):
        super().__init__()
        self.speed = 1.0
        self.deform_strength = 0.55
        self._ripples = []  # [(row, col, start_time)]
        self._lock = threading.Lock()
        self._ripple_life = 2.35
        self._ripple_radius = 6.2

    def trigger(self, row: int, col: int):
        with self._lock:
            self._ripples.append((row, col, time.time()))
            if len(self._ripples) > 24:
                self._ripples = self._ripples[-24:]

    def update(self, kb: WootFlowRGB, t: float):
        with self._lock:
            active = []
            for rr, rc, st in self._ripples:
                if t - st < self._ripple_life:
                    active.append((rr, rc, st))
            self._ripples = active

        base_speed = max(0.15, self.speed)
        deform = max(0.0, min(1.5, float(self.deform_strength)))

        for row, col in ALL_KEYS:
            x = col / 13.0
            y = row / max(1, WOOTING_RGB_ROWS - 1)

            # Campo de fluxo base com movimento lento e contínuo (corrente líquida).
            flow_x = x + math.sin((y * 7.2) + t * 1.45 * base_speed) * 0.06
            flow_y = y + math.sin((x * 6.6) - t * 1.25 * base_speed) * 0.05

            # Usado para brilho de interferência (caústica) após perturbações.
            ripple_energy = 0.0

            # Perturbação tipo água: frente de onda radial amortecida + pequena refração.
            for rr, rc, st in active:
                age = t - st
                dx = col - rc
                dy = row - rr
                dist = math.sqrt(dx * dx + dy * dy) + 1e-6
                if dist > self._ripple_radius:
                    continue

                life = max(0.0, 1.0 - age / self._ripple_life)
                radial_falloff = max(0.0, 1.0 - dist / self._ripple_radius)

                # Frente de onda desloca-se para fora como ondulação de água.
                wave_front = age * (2.3 + 0.45 * base_speed)
                phase = (dist - wave_front) * 5.4
                ring = math.sin(phase)

                # Amortecimento físico aproximado: cai com tempo e distância.
                damping = life * life * (radial_falloff ** 1.6)
                amplitude = deform * 0.085 * damping

                # Vetor radial (empurra/puxa conforme fase da onda).
                nx = dx / dist
                ny = dy / dist
                flow_x += nx * ring * amplitude
                flow_y += ny * ring * amplitude

                # Pequena componente tangencial para dar "twist" suave de fluido.
                tangent = math.cos(phase * 0.75 + age * 1.4) * amplitude * 0.28
                flow_x += -ny * tangent
                flow_y += nx * tangent

                ripple_energy += abs(ring) * damping

            f1 = math.sin((flow_x * 8.0 + flow_y * 4.0) + t * 1.9 * base_speed)
            f2 = math.sin((flow_x * 3.4 - flow_y * 7.1) - t * 1.35 * base_speed)
            f3 = math.sin((flow_x * 10.3 + flow_y * 2.4) + t * 0.9 * base_speed)
            mix = max(0.0, min(1.0, (f1 * 0.44 + f2 * 0.36 + f3 * 0.20 + 1.0) * 0.5))

            r, g, b = lerp_color(self.color1, self.color2, mix)

            # Brilho dinâmico com realce em zonas de interferência (efeito água viva).
            caustic = max(0.0, min(1.0, ripple_energy * 0.9))
            highlight = 0.9 + 0.18 * math.sin((flow_x + flow_y) * 8.3 + t * 2.2) + (0.22 * caustic)
            r, g, b = scale_color((r, g, b), self.brightness * max(0.2, highlight))
            kb.array_set_single(row, col, r, g, b)

        kb.array_update()


class JelloEffect(Effect):
    """Efeito elástico estilo jello: perturbação com oscilação amortecida."""
    name = "Jello"

    def __init__(self):
        super().__init__()
        self.speed = 1.0
        self._events = []  # [(row, col, start_time)]
        self._event_life = 1.6
        self._radius = 5.6
        self._lock = threading.Lock()

    def trigger(self, row: int, col: int):
        with self._lock:
            self._events.append((row, col, time.time()))
            if len(self._events) > 36:
                self._events = self._events[-36:]

    def update(self, kb: WootFlowRGB, t: float):
        with self._lock:
            alive = []
            for er, ec, st in self._events:
                if t - st < self._event_life:
                    alive.append((er, ec, st))
            self._events = alive

        base_speed = max(0.2, float(self.speed))

        for row, col in ALL_KEYS:
            x = col / 13.0
            y = row / max(1, WOOTING_RGB_ROWS - 1)

            # Base gelatinosa suave para manter movimento mesmo sem input.
            wobble = (
                math.sin((x * 10.0) + t * 2.0 * base_speed)
                + math.sin((y * 12.0) - t * 1.7 * base_speed)
                + math.sin(((x + y) * 8.5) + t * 1.3 * base_speed)
            ) / 3.0

            distortion = wobble * 0.22
            impulse = 0.0

            for er, ec, st in alive:
                age = t - st
                dx = col - ec
                dy = row - er
                dist = math.sqrt(dx * dx + dy * dy)
                if dist > self._radius:
                    continue

                life = max(0.0, 1.0 - age / self._event_life)
                radial = max(0.0, 1.0 - dist / self._radius)

                # Oscilação amortecida: dá aquele "abanão" elástico.
                osc = math.sin((dist * 2.6) - age * 13.0 * base_speed)
                ring = osc * (life ** 1.35) * (radial ** 1.8)
                distortion += ring * 0.85
                impulse += abs(ring)

            blend = max(0.0, min(1.0, 0.5 + distortion * 0.5))
            r, g, b = lerp_color(self.color1, self.color2, blend)

            # Realce rápido nas zonas onde o gel "treme" mais.
            shine = 0.92 + min(0.35, impulse * 0.42)
            r, g, b = scale_color((r, g, b), self.brightness * shine)
            kb.array_set_single(row, col, r, g, b)

        kb.array_update()


class TracersEffect(Effect):
    """Liga teclas com traços rápidos e persistentes; Space limpa tudo."""
    name = "Tracers"

    def __init__(self):
        super().__init__()
        self.speed = 1.0
        self.color1 = (0, 255, 200)
        self.color2 = (255, 80, 40)
        self._bg = (4, 4, 10)
        self._trace_seconds = 0.14
        self._max_points = 48
        self._max_segments = 96
        self._clear_keys = {(5, 4), (5, 5), (5, 6), (5, 7), (5, 8)} # Space 5 LEDS
        self._points = []      # [(row, col)]
        self._segments = []    # [{"keys": [...], "start": float}]
        self._lock = threading.Lock()

    def _line_keys(self, start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
        """Bresenham discreto para desenhar linha entre duas teclas."""
        r0, c0 = start
        r1, c1 = end
        dr = abs(r1 - r0)
        dc = abs(c1 - c0)
        sr = 1 if r0 < r1 else -1
        sc = 1 if c0 < c1 else -1

        keys = []
        if dc > dr:
            err = dc / 2
            while c0 != c1:
                if (r0, c0) in ALL_KEYS_SET:
                    keys.append((r0, c0))
                err -= dr
                if err < 0:
                    r0 += sr
                    err += dc
                c0 += sc
        else:
            err = dr / 2
            while r0 != r1:
                if (r0, c0) in ALL_KEYS_SET:
                    keys.append((r0, c0))
                err -= dc
                if err < 0:
                    c0 += sc
                    err += dr
                r0 += sr

        if (r1, c1) in ALL_KEYS_SET:
            keys.append((r1, c1))
        return keys

    def trigger(self, row: int, col: int):
        with self._lock:
            if (row, col) in self._clear_keys:
                self._points.clear()
                self._segments.clear()
                return

            new_point = (row, col)
            if self._points:
                prev = self._points[-1]
                if prev != new_point:
                    self._segments.append({
                        "keys": self._line_keys(prev, new_point),
                        "start": time.time(),
                    })
                    if len(self._segments) > self._max_segments:
                        self._segments = self._segments[-self._max_segments:]

            self._points.append(new_point)
            if len(self._points) > self._max_points:
                self._points = self._points[-self._max_points:]

    def update(self, kb: WootFlowRGB, t: float):
        with self._lock:
            points = list(self._points)
            segments = [
                {
                    "keys": list(seg["keys"]),
                    "start": float(seg["start"]),
                }
                for seg in self._segments
            ]

        for row, col in ALL_KEYS:
            kb.array_set_single(row, col, *self._bg)

        trace_duration = max(0.035, self._trace_seconds / max(0.2, self.speed))
        for seg in segments:
            line = seg["keys"]
            if not line:
                continue

            age = max(0.0, t - seg["start"])
            progress = max(0.0, min(1.0, age / trace_duration))
            draw_n = max(1, int(math.ceil(len(line) * progress)))

            tr, tg, tb = scale_color(self.color2, self.brightness)
            for row, col in line[:draw_n]:
                kb.array_set_single(row, col, tr, tg, tb)

        pr, pg, pb = scale_color(self.color1, self.brightness)
        for row, col in points:
            kb.array_set_single(row, col, pr, pg, pb)

        kb.array_update()


class LivingHeatmapEffect(Effect):
    """
    Efeito Living Heatmap — teclas aquecem gradualmente com cliques repetidos.
    
    Comportamento:
    - Cada clique adiciona +0.02 (precisa de ~50 cliques para máximo 1.0)
    - Cores: Verde Escuro → Amarelo → Laranja → Vermelho → Branco
    - Vizinhos aquecem 50% mais devagar (metade do valor da tecla principal)
    - Após 0.5s sem cliques, começa arrefecimento lento
    - Arrefecimento afeta tanto tecla principal como vizinhos
    """
    name = "Living Heatmap"

    def __init__(self):
        super().__init__()
        self.speed = 1.0  # controla velocidade de arrefecimento
        
        # Matriz de temperatura: [row][col] = 0.0 a 1.0
        self._temperature = [[0.0] * 21 for _ in range(6)]
        # Matriz de último tempo pressionado (para delay antes de arrefecer)
        self._last_press_time = [[0.0] * 21 for _ in range(6)]
        self._lock = threading.Lock()
        
        # Parâmetros de física
        self._press_heat = 0.02  # +0.02 por clique (50 cliques = 1.0)
        self._cooldown_delay = 0.5  # aguarda 0.5s antes de arrefecer
        self._cooldown_rate = 0.15  # velocidade de arrefecimento (0.15/seg)
        self._neighbor_factor = 0.5  # vizinhos aquecem 50% (metade)

    def trigger(self, row: int, col: int):
        """Registra uma tecla pressionada — incrementa temperatura."""
        if 0 <= row < 6 and 0 <= col < 21:
            with self._lock:
                current_time = time.time()
                self._temperature[row][col] = min(
                    1.0,
                    self._temperature[row][col] + self._press_heat
                )
                # Registar tempo do pressionamento (para delay antes de arrefecer)
                self._last_press_time[row][col] = current_time
                
                # Também aquecer vizinhos, mas 50% mais devagar
                neighbors = self._get_neighbors(row, col)
                for nr, nc in neighbors:
                    self._temperature[nr][nc] = min(
                        1.0,
                        self._temperature[nr][nc] + self._press_heat * self._neighbor_factor
                    )

    def _get_neighbors(self, row: int, col: int) -> list[tuple[int, int]]:
        """Retorna teclas vizinhas (8 direções + diagonais)."""
        neighbors = []
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0:
                    continue
                nr, nc = row + dr, col + dc
                if 0 <= nr < 6 and 0 <= nc < 21 and (nr, nc) in ALL_KEYS_SET:
                    neighbors.append((nr, nc))
        return neighbors

    def _temperature_to_color(self, temp: float) -> tuple[int, int, int]:
        """Mapeia temperatura para cor com transição suave.
        
        0.0 → Verde escuro (5, 80, 20)
        0.25 → Amarelo (255, 220, 0)
        0.5 → Laranja (255, 140, 0)
        0.75 → Vermelho (255, 40, 0)
        1.0 → Branco (255, 255, 255)
        """
        temp = max(0.0, min(1.0, temp))
        
        if temp == 0.0:
            # Verde escuro (inativo)
            return (5, 80, 20)
        elif temp < 0.25:
            # Verde escuro → Amarelo (0.0-0.25)
            t = temp / 0.25
            r = int(5 + (255 - 5) * t)
            g = int(80 + (220 - 80) * t)
            b = int(20 + (0 - 20) * t)
        elif temp < 0.5:
            # Amarelo → Laranja (0.25-0.5)
            t = (temp - 0.25) / 0.25
            r = 255
            g = int(220 + (140 - 220) * t)
            b = int(0 + (0 - 0) * t)
        elif temp < 0.75:
            # Laranja → Vermelho (0.5-0.75)
            t = (temp - 0.5) / 0.25
            r = 255
            g = int(140 + (40 - 140) * t)
            b = int(0 + (0 - 0) * t)
        else:
            # Vermelho → Branco (0.75-1.0)
            t = (temp - 0.75) / 0.25
            r = int(255 + (255 - 255) * t)
            g = int(40 + (255 - 40) * t)
            b = int(0 + (255 - 0) * t)
        
        # Flicker leve no estado quente (>0.8)
        if temp > 0.8:
            flicker = 0.85 + 0.15 * math.sin(time.time() * 12.0)
            r = min(255, int(r * flicker))
            g = min(255, int(g * flicker))
            b = min(255, int(b * flicker))
        
        return (r, g, b)

    def update(self, kb: WootFlowRGB, t: float):
        """Atualiza o efeito: arrefecimento após delay e renderização."""
        dt = 1.0 / 60.0  # assume 60fps
        
        with self._lock:
            current_time = t
            
            # Arrefecimento gradual (apenas se passou 0.5s sem cliques)
            for row in range(6):
                for col in range(21):
                    if (row, col) not in ALL_KEYS_SET:
                        continue
                    
                    time_since_press = current_time - self._last_press_time[row][col]
                    
                    # Só arrefece se passou 0.5s sem cliques
                    if time_since_press >= self._cooldown_delay:
                        cooldown_speed = self._cooldown_rate * self.speed * dt
                        self._temperature[row][col] = max(
                            0.0,
                            self._temperature[row][col] - cooldown_speed
                        )
            
            temps = [row[:] for row in self._temperature]
        
        # Renderização
        for row, col in ALL_KEYS:
            temp = temps[row][col]
            
            # Cor baseada na temperatura
            r, g, b = self._temperature_to_color(temp)
            
            # Glow dinâmico: mais brilho conforme aumenta temperatura
            glow_factor = 0.3 + 0.7 * temp  # 0.3 a 1.0
            glow_factor *= self.brightness
            
            # Aplicar glow
            r = min(255, int(r * glow_factor))
            g = min(255, int(g * glow_factor))
            b = min(255, int(b * glow_factor))
            
            kb.array_set_single(row, col, r, g, b)
        
        kb.array_update()


# ============================================================================
# Equalizer: mapa de colunas físicas e cor por altura
# ============================================================================

# Teclas físicas por coluna SDK (rows de baixo para cima)
EQ_COLUMNS = {}  # col → [rows bottom-first]


def _rebuild_eq_columns():
    EQ_COLUMNS.clear()
    for row_keys in PHYSICAL_KEYS_60HE:
        for r, c in row_keys:
            EQ_COLUMNS.setdefault(c, []).append(r)
    for c in EQ_COLUMNS:
        EQ_COLUMNS[c].sort(reverse=True)  # bottom row first


_rebuild_eq_columns()


def _resample(values: list[float], n: int) -> list[float]:
    """Ajusta as bandas de áudio ao nº de colunas do teclado (interpolação linear)."""
    if len(values) == n:
        return list(values)
    if not values:
        return [0.0] * n
    if n == 1:
        return [float(values[0])]
    out = []
    for i in range(n):
        pos = i * (len(values) - 1) / (n - 1)
        lo = int(pos)
        hi = min(lo + 1, len(values) - 1)
        out.append(values[lo] + (values[hi] - values[lo]) * (pos - lo))
    return out


def eq_height_color(pos: int, total: int) -> tuple[int, int, int]:
    """Cor do equalizer clássico: verde (base) → amarelo → vermelho (topo)."""
    if total <= 1:
        return (0, 220, 0)
    t = pos / (total - 1)  # 0.0 = bottom, 1.0 = top
    if t < 0.5:
        t2 = t * 2
        return (int(255 * t2), 220 + int(35 * t2), 0)
    else:
        t2 = (t - 0.5) * 2
        return (255, int(255 * (1 - t2)), 0)


class EqualizerEffect(Effect):
    """
    Efeito equalizer clássico — cada coluna = 1 banda de frequência.
    Graves à esquerda, agudos à direita. Cor por altura: verde → amarelo → vermelho.
    Respeita o layout físico do 60HE (colunas com nº diferente de teclas).
    """
    name = "Equalizer"

    def __init__(self):
        super().__init__()
        self._bands = [0.0] * LAYOUT_COLS
        self._peaks = [0.0] * LAYOUT_COLS
        self._lock = threading.Lock()

    def set_bands(self, bands: list[float], peaks: list[float] = None):
        """Atualiza os dados de frequência."""
        with self._lock:
            self._bands = _resample(bands, LAYOUT_COLS)
            if peaks:
                self._peaks = _resample(peaks, LAYOUT_COLS)

    def update(self, kb: WootFlowRGB, t: float):
        with self._lock:
            bands = self._bands.copy()
            peaks = self._peaks.copy()

        for col in range(LAYOUT_COLS):
            col_rows = EQ_COLUMNS.get(col, [])
            num_keys = len(col_rows)
            if num_keys == 0:
                continue

            band_val = bands[col] if col < len(bands) else 0.0
            peak_val = peaks[col] if col < len(peaks) else 0.0
            fill = band_val * num_keys  # quantas teclas preencher
            peak_idx = min(int(peak_val * (num_keys - 1)), num_keys - 1)

            for i, row in enumerate(col_rows):
                # i=0 → tecla de baixo, i=num_keys-1 → tecla de cima
                base_color = eq_height_color(i, num_keys)

                if i < fill:
                    intensity = self.brightness
                    if i >= int(fill):
                        intensity *= (fill - int(fill))
                    r, g, b = scale_color(base_color, intensity)
                    kb.array_set_single(row, col, r, g, b)
                elif i == peak_idx and peak_val > 0.08:
                    r, g, b = scale_color(base_color, 0.5 * self.brightness)
                    kb.array_set_single(row, col, r, g, b)
                else:
                    kb.array_set_single(row, col, 3, 3, 3)

        kb.array_update()


# ============================================================================
# Registo de efeitos
# ============================================================================

EFFECTS = {
    "solid_color": SolidColorEffect,
    "gradient": GradientEffect,
    "rainbow_wave": RainbowWaveEffect,
    "color_wave": ColorWaveEffect,
    "breathing": BreathingEffect,
    "spectrum_cycle": SpectrumCycleEffect,
    "ripple": RippleEffect,
    "reactive_typing": ReactiveTypingEffect,
    "fire": FireEffect,
    "matrix_rain": MatrixRainEffect,
    "starfield": StarfieldEffect,
    "aurora": AuroraEffect,
    "raindrop": RaindropEffect,
    "sparkle": SparkleEffect,
    "heartbeat": HeartbeatEffect,
    "lava": LavaEffect,
    "ocean": OceanEffect,
    "liquid_flow": LiquidFlowEffect,
    "magnetic_keys": MagneticKeysEffect,
    "jello": JelloEffect,
    "tracers": TracersEffect,
    "living_heatmap": LivingHeatmapEffect,
}

EFFECT_NAMES = {
    "solid_color": "Solid Color",
    "gradient": "Gradient",
    "rainbow_wave": "Rainbow Wave",
    "color_wave": "Color Wave",
    "breathing": "Breathing",
    "spectrum_cycle": "Spectrum Cycle",
    "ripple": "Ripple",
    "reactive_typing": "Reactive Typing",
    "fire": "Fire",
    "matrix_rain": "Matrix Rain",
    "starfield": "Starfield",
    "aurora": "Aurora",
    "raindrop": "Raindrop",
    "sparkle": "Sparkle",
    "heartbeat": "Heartbeat",
    "lava": "Lava",
    "ocean": "Ocean",
    "liquid_flow": "Liquid Flow",
    "magnetic_keys": "Magnetic Keys",
    "jello": "Jello",
    "tracers": "Tracers",
    "living_heatmap": "Living Heatmap",
}
