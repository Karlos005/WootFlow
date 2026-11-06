"""
Deteção do teclado Wooting ligado e perfil de layout usado pelos efeitos.

O SDK RGB expõe sempre uma matriz (até 6x21); o que muda de modelo para modelo
é que posições têm LED físico. O 60HE tem layout medido (ISO PT); os restantes
formatos usam a grelha completa devolvida pelo SDK, o que é uma aproximação
(inclui posições sem LED) até haver um mapa medido para cada modelo.
"""

from dataclasses import dataclass, field

WOOTING_VID = 0x31E3

# Valores de WOOTING_DEVICE_TYPE em sdk/wooting-usb.h.
FORM_FACTOR_BY_TYPE = {
    1: "TKL",
    2: "Full",
    3: "60%",
    4: "3KL",
    5: "80%",
}

# Layout medido do 60HE ISO: linhas do SDK 1..5 (sem a linha de F-keys).
_KEYS_60HE = [
    [(1, c) for c in range(14)],
    [(2, c) for c in range(13)],
    [(3, c) for c in range(14)],
    [(4, c) for c in range(12)] + [(4, 13)],
    [(5, 0), (5, 1), (5, 2), (5, 4), (5, 5), (5, 6), (5, 7), (5, 8),
     (5, 10), (5, 11), (5, 12), (5, 13)],
]


@dataclass(frozen=True)
class KeyboardProfile:
    """Descreve o teclado para os efeitos que dependem da posição das teclas."""
    key: str                      # identificador estável, ex.: "60", "tkl"
    name: str                     # nome para mostrar na UI
    form_factor: str
    rows: int
    cols: int
    keys: tuple                   # linhas de (row, col) com LED
    layout: str = "ISO"
    measured: bool = False        # False = grelha aproximada
    model: str = ""
    usb_pid: int | None = None
    extra: dict = field(default_factory=dict, compare=False)

    @property
    def key_count(self) -> int:
        return sum(len(r) for r in self.keys)

    @property
    def band_count(self) -> int:
        return len({c for row in self.keys for _, c in row})

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "model": self.model,
            "form_factor": self.form_factor,
            "layout": self.layout,
            "rows": self.rows,
            "cols": self.cols,
            "key_count": self.key_count,
            "band_count": self.band_count,
            "measured": self.measured,
            "usb_pid": self.usb_pid,
        }


def _full_grid(rows: int, cols: int) -> tuple:
    return tuple(tuple((r, c) for c in range(cols)) for r in range(rows))


def profile_from_device_info(info: dict | None, usb_pid: int | None = None) -> KeyboardProfile:
    """Escolhe o perfil a partir do que o SDK devolve (get_device_info)."""
    if not info:
        return default_profile()

    model = str(info.get("model") or "")
    factor = str(info.get("device_type") or "")
    layout = str(info.get("layout") or "ISO")
    rows = int(info.get("max_rows") or 6)
    cols = int(info.get("max_columns") or 21)

    is_60 = "60" in factor or "60" in model
    if is_60:
        return KeyboardProfile(
            key="60", name=model or "Wooting 60%", form_factor="60%",
            rows=rows, cols=cols, keys=tuple(tuple(r) for r in _KEYS_60HE),
            layout=layout, measured=True, model=model, usb_pid=usb_pid,
        )

    short = factor.replace("Keyboard", "").strip() or "Keyboard"
    return KeyboardProfile(
        key=short.lower().replace(" ", "") or "keyboard",
        name=model or f"Wooting {short}", form_factor=short,
        rows=rows, cols=cols, keys=_full_grid(rows, cols),
        layout=layout, measured=False, model=model, usb_pid=usb_pid,
    )


def default_profile() -> KeyboardProfile:
    """Perfil usado sem teclado ligado: o 60HE para o qual os efeitos foram feitos."""
    return KeyboardProfile(
        key="60", name="Wooting 60HE", form_factor="60%", rows=6, cols=21,
        keys=tuple(tuple(r) for r in _KEYS_60HE), layout="ISO", measured=True,
    )
