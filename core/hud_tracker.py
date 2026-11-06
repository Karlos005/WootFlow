"""Leitura de barras do HUD de um jogo a partir do ecrã.

É o que as integrações de jogos do SignalRGB fazem para jogos sem API: olhar para
uma zona do ecrã (por exemplo a barra de vida) e medir quanto dela está cheia.
Aqui cada "medidor" define uma região, a cor da barra e a linha do teclado onde
o valor é mostrado.
"""
from __future__ import annotations

import base64
import io
import threading
import time
from dataclasses import dataclass, field

import numpy as np

MAX_METERS = 6
POLL_HZ = 10
MIN_COLUMN_COVERAGE = 0.35   # fração de uma coluna que tem de ter a cor da barra
DROP_FLASH_THRESHOLD = 0.04  # queda mínima (0..1) que conta como "levei dano"
FLASH_SECONDS = 0.35
SMOOTHING = 0.5


def _clamp(value, lo, hi, default):
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return default


def _color(value, default):
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return tuple(max(0, min(255, int(v))) for v in value[:3])
        except (TypeError, ValueError):
            pass
    return default


@dataclass
class Meter:
    id: str
    name: str
    region: tuple              # x, y, largura, altura — normalizados (0..1) no monitor
    color: tuple               # cor da barra no HUD
    tolerance: int = 60        # distância RGB máxima (0..441) para contar como "barra"
    orientation: str = "horizontal"
    row: int = 1               # linha do teclado (1..5) onde se mostra
    color_full: tuple = (0, 255, 60)
    color_empty: tuple = (255, 0, 0)
    low_threshold: float = 0.25
    flash_on_drop: bool = True

    @classmethod
    def from_dict(cls, data, index: int = 0) -> "Meter | None":
        if not isinstance(data, dict):
            return None
        region = data.get("region")
        if not isinstance(region, (list, tuple)) or len(region) != 4:
            return None
        x = _clamp(region[0], 0.0, 1.0, None)
        y = _clamp(region[1], 0.0, 1.0, None)
        w = _clamp(region[2], 0.0, 1.0, None)
        h = _clamp(region[3], 0.0, 1.0, None)
        if None in (x, y, w, h) or w < 0.005 or h < 0.003:
            return None
        w, h = min(w, 1.0 - x), min(h, 1.0 - y)
        if w < 0.005 or h < 0.003:
            return None
        color = _color(data.get("color"), None)
        if color is None:
            return None
        meter_id = str(data.get("id") or f"m{index + 1}")[:16]
        row = int(_clamp(data.get("row", 1), 1, 5, 1))
        return cls(
            id=meter_id,
            name=str(data.get("name") or f"Medidor {index + 1}").strip()[:40],
            region=(x, y, w, h),
            color=color,
            tolerance=int(_clamp(data.get("tolerance", 60), 5, 300, 60)),
            orientation="vertical" if data.get("orientation") == "vertical" else "horizontal",
            row=row,
            color_full=_color(data.get("color_full"), (0, 255, 60)),
            color_empty=_color(data.get("color_empty"), (255, 0, 0)),
            low_threshold=_clamp(data.get("low_threshold", 0.25), 0.0, 1.0, 0.25),
            flash_on_drop=bool(data.get("flash_on_drop", True)),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "region": list(self.region),
            "color": list(self.color), "tolerance": self.tolerance,
            "orientation": self.orientation, "row": self.row,
            "color_full": list(self.color_full), "color_empty": list(self.color_empty),
            "low_threshold": self.low_threshold, "flash_on_drop": self.flash_on_drop,
        }


@dataclass
class HudConfig:
    monitor: int = 0
    meters: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, data) -> "HudConfig | None":
        if not isinstance(data, dict):
            return None
        meters = []
        seen = set()
        for i, item in enumerate(data.get("meters") or []):
            meter = Meter.from_dict(item, i)
            if meter and meter.id not in seen:
                seen.add(meter.id)
                meters.append(meter)
        if not meters:
            return None
        return cls(monitor=int(_clamp(data.get("monitor", 0), 0, 7, 0)), meters=meters[:MAX_METERS])

    def to_dict(self) -> dict:
        return {"monitor": self.monitor, "meters": [m.to_dict() for m in self.meters]}


def measure_fraction(image: np.ndarray, meter: Meter) -> float:
    """Fração (0..1) da região (já recortada) cuja cor é a da barra do medidor."""
    if image.size == 0:
        return 0.0
    diff = image[:, :, :3].astype(np.int32) - np.array(meter.color, dtype=np.int32)
    match = (diff * diff).sum(axis=2) <= meter.tolerance ** 2
    axis = 0 if meter.orientation == "horizontal" else 1  # cobertura por coluna / linha
    coverage = match.mean(axis=axis)
    return float((coverage >= MIN_COLUMN_COVERAGE).mean())


def _new_mss():
    """`mss.MSS` nas versões novas; `mss.mss` nas antigas."""
    import mss
    return getattr(mss, "MSS", None)() if hasattr(mss, "MSS") else mss.mss()


def _monitor_box(sct, monitor: int):
    monitors = sct.monitors  # [0] = todos os monitores
    if monitor + 1 >= len(monitors):
        return None
    return monitors[monitor + 1]


def _grab_region(sct, mon: dict, region: tuple) -> np.ndarray:
    left = mon["left"] + int(region[0] * mon["width"])
    top = mon["top"] + int(region[1] * mon["height"])
    width = max(1, int(region[2] * mon["width"]))
    height = max(1, int(region[3] * mon["height"]))
    shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
    return np.asarray(shot)[:, :, 2::-1].copy()  # BGRA -> RGB


def list_monitors() -> list:
    with _new_mss() as sct:
        return [
            {"index": i - 1, "width": m["width"], "height": m["height"],
             "primary": bool(m.get("is_primary", False))}
            for i, m in enumerate(sct.monitors) if i > 0
        ]


def capture_png_data_url(monitor: int, max_width: int = 1920) -> dict | None:
    """Screenshot do monitor como data URL, para o utilizador escolher regiões."""
    from PIL import Image
    with _new_mss() as sct:
        mon = _monitor_box(sct, monitor)
        if mon is None:
            return None
        shot = sct.grab(mon)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    if img.width > max_width:
        img = img.resize((max_width, round(img.height * max_width / img.width)))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return {
        "width": img.width, "height": img.height,
        "image": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii"),
    }


def probe(monitor: int, meter: Meter) -> float | None:
    """Mede um medidor uma só vez no ecrã atual (usado na calibração)."""
    with _new_mss() as sct:
        mon = _monitor_box(sct, monitor)
        if mon is None:
            return None
        return measure_fraction(_grab_region(sct, mon, meter.region), meter)


class HudTracker:
    """Thread que mede os medidores ~10x por segundo enquanto há um perfil com HUD."""

    def __init__(self):
        self._lock = threading.Lock()
        self._config: HudConfig | None = None
        self._values: dict = {}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.error: str | None = None

    def configure(self, config: "HudConfig | None") -> None:
        with self._lock:
            self._config = config
            self._values = {}

    def meters(self) -> list:
        with self._lock:
            return list(self._config.meters) if self._config else []

    def snapshot(self, now: float | None = None) -> dict:
        """{id: {"fraction", "flash", "age"}}; `flash` é 1 quando acabou de haver dano e decai a 0."""
        now = time.time() if now is None else now
        with self._lock:
            out = {}
            for meter_id, v in self._values.items():
                flash = max(0.0, (v["flash_until"] - now) / FLASH_SECONDS)
                out[meter_id] = {"fraction": v["fraction"], "flash": min(1.0, flash), "age": now - v["t"]}
            return out

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="hud-tracker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            self._values = {}

    def update_from_frames(self, readings: dict, now: float) -> None:
        """Aplica leituras novas {id: fração}: suaviza e deteta quedas (dano)."""
        with self._lock:
            meters = {m.id: m for m in (self._config.meters if self._config else [])}
            for meter_id, raw in readings.items():
                meter = meters.get(meter_id)
                if meter is None:
                    continue
                prev = self._values.get(meter_id)
                if prev is None:
                    self._values[meter_id] = {"fraction": raw, "flash_until": 0.0, "t": now}
                    continue
                smooth = prev["fraction"] + (raw - prev["fraction"]) * SMOOTHING
                flash_until = prev["flash_until"]
                if meter.flash_on_drop and prev["fraction"] - smooth >= DROP_FLASH_THRESHOLD:
                    flash_until = now + FLASH_SECONDS
                self._values[meter_id] = {"fraction": smooth, "flash_until": flash_until, "t": now}

    def _run(self) -> None:
        try:
            sct = _new_mss()  # as instâncias do mss pertencem à thread que as cria
        except Exception as exc:
            self.error = f"Captura de ecrã indisponível: {exc}"
            return
        period = 1.0 / POLL_HZ
        try:
            while not self._stop.is_set():
                with self._lock:
                    config = self._config
                if config:
                    mon = _monitor_box(sct, config.monitor)
                    if mon is not None:
                        readings = {}
                        for meter in config.meters:
                            try:
                                readings[meter.id] = measure_fraction(_grab_region(sct, mon, meter.region), meter)
                            except Exception as exc:  # um frame mau não pára o resto
                                self.error = str(exc)
                        self.update_from_frames(readings, time.time())
                self._stop.wait(period)
        finally:
            sct.close()


TRACKER = HudTracker()
