"""Actuation point / Rapid Trigger logic for analog (Hall-effect) keys.

Pure logic, no hardware access: feed it key travel in millimetres and it
reports whether the key counts as pressed. Per-key tuning is stored in
`AnalogTuning` and persisted by the server alongside the other settings.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

MAX_TRAVEL_MM = 4.0
MIN_ACTUATION_MM = 0.1
RESET_FLOOR_MM = 0.1  # below this the key is always considered fully released
MIN_SENSITIVITY_MM = 0.1


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


@dataclass
class KeyTuning:
    actuation_mm: float = 1.5
    rapid_trigger: bool = False
    separate_sensitivity: bool = False
    sensitivity_mm: float = 0.4       # used for both directions unless separate
    upstroke_mm: float = 0.4
    downstroke_mm: float = 0.4

    def normalized(self) -> "KeyTuning":
        return KeyTuning(
            actuation_mm=round(_clamp(self.actuation_mm, MIN_ACTUATION_MM, MAX_TRAVEL_MM), 2),
            rapid_trigger=bool(self.rapid_trigger),
            separate_sensitivity=bool(self.separate_sensitivity),
            sensitivity_mm=round(_clamp(self.sensitivity_mm, MIN_SENSITIVITY_MM, MAX_TRAVEL_MM), 2),
            upstroke_mm=round(_clamp(self.upstroke_mm, MIN_SENSITIVITY_MM, MAX_TRAVEL_MM), 2),
            downstroke_mm=round(_clamp(self.downstroke_mm, MIN_SENSITIVITY_MM, MAX_TRAVEL_MM), 2),
        )

    @property
    def up(self) -> float:
        return self.upstroke_mm if self.separate_sensitivity else self.sensitivity_mm

    @property
    def down(self) -> float:
        return self.downstroke_mm if self.separate_sensitivity else self.sensitivity_mm


class RapidTriggerEngine:
    """Per-key press state machine driven by analog travel (mm).

    Without Rapid Trigger the key is pressed while travel >= actuation point.
    With it, the first press still needs the actuation point; afterwards the
    key releases as soon as it rises `up` mm from its deepest point and presses
    again as soon as it sinks `down` mm from its shallowest point, until it
    returns to the reset floor.
    """

    def __init__(self, tuning: KeyTuning):
        self.tuning = tuning.normalized()
        self.pressed = False
        self._armed = False   # Rapid Trigger is tracking since the first actuation
        self._extreme = 0.0   # deepest point while pressed, shallowest while released

    def set_tuning(self, tuning: KeyTuning) -> None:
        self.tuning = tuning.normalized()

    def update(self, travel_mm: float) -> bool:
        """Feed the latest travel; returns the new pressed state."""
        t = self.tuning
        mm = _clamp(travel_mm, 0.0, MAX_TRAVEL_MM)

        if mm <= RESET_FLOOR_MM:
            self.pressed = False
            self._armed = False
            self._extreme = 0.0
            return False

        if not t.rapid_trigger:
            self.pressed = mm >= t.actuation_mm
            self._armed = False
            return self.pressed

        if not self._armed:
            if mm >= t.actuation_mm:
                self.pressed = self._armed = True
                self._extreme = mm
        elif self.pressed:
            self._extreme = max(self._extreme, mm)
            if mm <= self._extreme - t.up:
                self.pressed = False
                self._extreme = mm
        else:
            self._extreme = min(self._extreme, mm)
            if mm >= self._extreme + t.down:
                self.pressed = True
                self._extreme = mm
        return self.pressed


@dataclass
class AnalogTuning:
    """Settings for every key plus the global tachyon flag."""

    default: KeyTuning = field(default_factory=KeyTuning)
    keys: dict[str, KeyTuning] = field(default_factory=dict)  # "row-col" -> tuning
    tachyon: bool = False

    def for_key(self, key_id: str) -> KeyTuning:
        return self.keys.get(key_id, self.default)

    def apply(self, key_ids: list[str], patch: dict) -> None:
        """Merge `patch` (camelCase from the UI) into each selected key."""
        for key_id in key_ids:
            current = self.for_key(key_id)
            data = asdict(current)
            for src, dst in (
                ("actuationMm", "actuation_mm"),
                ("rapidTrigger", "rapid_trigger"),
                ("separateSensitivity", "separate_sensitivity"),
                ("sensitivityMm", "sensitivity_mm"),
                ("upstrokeMm", "upstroke_mm"),
                ("downstrokeMm", "downstroke_mm"),
            ):
                if src in patch:
                    data[dst] = patch[src]
            self.keys[key_id] = KeyTuning(**data).normalized()

    def to_dict(self) -> dict:
        return {
            "tachyon": self.tachyon,
            "default": asdict(self.default),
            "keys": {k: asdict(v) for k, v in self.keys.items()},
        }

    @classmethod
    def from_dict(cls, raw: dict | None) -> "AnalogTuning":
        raw = raw or {}
        out = cls(tachyon=bool(raw.get("tachyon", False)))
        try:
            out.default = KeyTuning(**raw.get("default", {})).normalized()
            out.keys = {k: KeyTuning(**v).normalized() for k, v in raw.get("keys", {}).items()}
        except TypeError:
            pass  # corrupt settings file: keep defaults
        return out
