"""Central effect registry for runtime usage."""

from core.effects_engine import EFFECTS as _EFFECTS
from core.effects_engine import EFFECT_NAMES as _EFFECT_NAMES

EFFECT_REGISTRY = dict(_EFFECTS)
EFFECT_LABELS = dict(_EFFECT_NAMES)

# Efeitos que dependem de dados do jogo (leitura do HUD no ecrã)
from core.hud_effect import HudMetersEffect as _HudMetersEffect  # noqa: E402

EFFECT_REGISTRY["hud_meters"] = _HudMetersEffect
EFFECT_LABELS["hud_meters"] = "HUD do jogo (leitura do ecrã)"


def get_effect_class(name: str):
    return EFFECT_REGISTRY.get(name)


def list_effect_items():
    return sorted(EFFECT_LABELS.items(), key=lambda pair: pair[1].lower())
