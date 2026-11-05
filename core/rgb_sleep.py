"""Modo de suspensão RGB: diminui o brilho e depois apaga após inatividade."""

# Passos do Wootility, em minutos; None = nunca.
SLEEP_STEPS: tuple = (1, 3, 5, 10, 20, 30, 60, None)
DIM_LEVEL = 0.2


def normalize_minutes(value) -> int | None:
    """Aceita só um dos passos válidos; qualquer outra coisa conta como "nunca"."""
    if value in SLEEP_STEPS[:-1] and not isinstance(value, bool):
        return int(value)
    return None


def sleep_factor(idle_seconds: float, dim_min: int | None, off_min: int | None) -> float:
    """Multiplicador de brilho (1 = normal, 0 = apagado) para o tempo sem premir teclas."""
    if off_min is not None and idle_seconds >= off_min * 60:
        return 0.0
    if dim_min is not None and idle_seconds >= dim_min * 60:
        return DIM_LEVEL
    return 1.0
