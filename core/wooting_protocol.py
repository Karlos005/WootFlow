"""Wooting configuration protocol: pure encoders for actuation / Rapid Trigger.

Derived from static analysis of the Wootility renderer bundle (v5.4.2); see
docs/wooting-hid-protocol.md for the evidence and open questions. Nothing here
touches hardware: every function returns bytes that a HID transport would send.

Wire summary
------------
* Query  = 7-byte HID *feature report*: magic(2 LE) | command(1) | param(4 LE)
* Update = HID *output report*: magic(2 LE) | command(1) | options(1) |
           length(1, or 2 LE for the 0xDAD1 "multi" interface) | protobuf payload
* options byte = save(bit0) | profile index(bits 1-5) | namespace(bits 6-7)
"""
from __future__ import annotations

from math import floor

MAGIC_LEGACY = 0xDAD0  # 1-byte length (V1/V2 interfaces)
MAGIC_MULTI = 0xDAD1   # 2-byte length (usage page 0xFF55)

CMD_SET_ACTUATION = 21
CMD_SET_RAPID_TRIGGER = 25
CMD_SET_FULL_RAPID_TRIGGER = 29
CMD_GET_ANALOG_VALUES = 20
CMD_GET_ACTUATION = 49
CMD_GET_RAPID_TRIGGER = 54
CMD_GET_FULL_RAPID_TRIGGER = 61

NAMESPACE_ONBOARD = 0
PARTIAL_THRESHOLD = 50   # Wootility sends a full matrix once >= 50 keys change
HE_TRAVEL_MM = 4.0       # Hall-effect devices: raw 255 == 4.0 mm
FORMAT_8BIT = 0
FORMAT_14BIT = 1
MAX_14BIT = 16383


def _js_round(x: float) -> int:
    """Math.round semantics (halves go up), unlike Python's banker's rounding."""
    return int(floor(x + 0.5))


# ── key / value encoding ────────────────────────────────────────────────────
def key_index(row: int, col: int) -> int:
    """Wootility matrix cell -> 1-byte key index (row in bits 5-7, col in 0-4)."""
    if not (0 <= row <= 5 and 0 <= col <= 31) or (row, col) == (5, 31):
        raise ValueError(f"key out of range: row={row} col={col}")
    return (row & 7) << 5 | (col & 31)


def mm_to_raw8(mm: float) -> int:
    """Millimetres -> 0..255 raw travel (Hall-effect scale)."""
    mm = max(0.0, min(HE_TRAVEL_MM, mm))
    return _js_round(mm / HE_TRAVEL_MM * 255)


def encode_value(mm: float, fmt: int = FORMAT_8BIT) -> int:
    raw = mm_to_raw8(mm)
    if fmt == FORMAT_8BIT:
        return raw
    if fmt == FORMAT_14BIT:
        return (_js_round(raw * MAX_14BIT / 255) & MAX_14BIT) | 0x4000
    raise ValueError(f"unknown format {fmt}")


# ── minimal protobuf writer ─────────────────────────────────────────────────
def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _tag(field: int, wire: int) -> bytes:
    return _varint(field << 3 | wire)


def _ld(field: int, payload: bytes) -> bytes:
    return _tag(field, 2) + _varint(len(payload)) + payload


def _uint(field: int, value: int) -> bytes:
    return _tag(field, 0) + _varint(value)


# ── profile messages ────────────────────────────────────────────────────────
def encode_actuation_partial(values_mm: dict[tuple[int, int], float], fmt: int = FORMAT_8BIT) -> bytes:
    """KeyMMPropertyProfile with a sparse set of keys (profiles.KeyMMPropertyProfile).

    8-bit entries are `value << 8 | keyIndex`; 14-bit entries `value << 16 | keyIndex`
    and travel in the `partialEncoded` (field 4) arm instead of `partial` (field 2).
    """
    shift, arm = (8, 2) if fmt == FORMAT_8BIT else (16, 4)
    body = b"".join(
        _uint(1, encode_value(mm, fmt) << shift | key_index(r, c))  # unpacked repeated uint32
        for (r, c), mm in sorted(values_mm.items())
    )
    return _ld(arm, body)


def encode_actuation_full(matrix_mm: list[list[float | None]]) -> bytes:
    """KeyMMPropertyProfile `full` arm: one byte per cell, 8-bit format only."""
    rows = b"".join(
        _ld(1, _ld(1, bytes(0 if v is None else mm_to_raw8(v) for v in row)))
        for row in matrix_mm
    )
    return _ld(1, rows)


def encode_per_key_rapid_trigger(enabled: dict[tuple[int, int], bool]) -> bytes:
    """KeyPropertyProfile for the simple per-key RT switch: 2 = on, 1 = off."""
    body = b"".join(
        _uint(1, (2 if on else 1) << 8 | key_index(r, c)) for (r, c), on in sorted(enabled.items())
    )
    return _ld(2, body)


def encode_full_rapid_trigger(
    groups: list[dict],
    fmt: int = FORMAT_8BIT,
) -> bytes:
    """RapidTriggerProfile: groups of keys sharing one config.

    Each group: {"keys": [(row, col), ...]} plus either {"enabled": bool} or
    {"sensitivity_mm", "secondary_sensitivity_mm"?, "strict_actuation_range"?}.
    `secondary_sensitivity_mm` unset means up/down share `sensitivity_mm`.
    """
    out = b""
    for g in groups:
        msg = b"".join(_uint(1, key_index(r, c)) for r, c in g["keys"])
        if "enabled" in g:
            msg += _uint(3, 1 if g["enabled"] else 0)
        else:
            cfg = _uint(1, encode_value(g["sensitivity_mm"], fmt))
            if g.get("secondary_sensitivity_mm") is not None:
                cfg += _uint(2, encode_value(g["secondary_sensitivity_mm"], fmt))
            if g.get("strict_actuation_range") is False:  # continuousMode = !strict
                cfg += _uint(3, 1)
            msg += _ld(2, cfg)
        out += _ld(1, msg)
    return out


# ── packets ─────────────────────────────────────────────────────────────────
def _profile_param(profile_index: int | None, namespace: int = NAMESPACE_ONBOARD) -> int:
    return 0xFFFF if profile_index is None else ((namespace << 8) | profile_index) & 0xFFFF


def query_packet(command: int, profile_index: int | None = None, magic: int = MAGIC_LEGACY) -> bytes:
    """7-byte feature-report body for a read command (get*Profile, getAnalogValues)."""
    return (
        magic.to_bytes(2, "little")
        + bytes([command])
        + _profile_param(profile_index).to_bytes(4, "little")
    )


def update_packet(
    command: int,
    payload: bytes,
    *,
    save: bool = False,
    profile_index: int = 0,
    namespace: int = NAMESPACE_ONBOARD,
    magic: int = MAGIC_LEGACY,
) -> bytes:
    """Output-report body for a write command. `save=False` leaves flash untouched."""
    options = (1 if save else 0) | (profile_index & 31) << 1 | (namespace & 3) << 6
    length = (
        len(payload).to_bytes(2, "little") if magic == MAGIC_MULTI else len(payload).to_bytes(1, "little")
    )
    if magic != MAGIC_MULTI and len(payload) > 255:
        raise ValueError("payload too long for the legacy 1-byte length field")
    return magic.to_bytes(2, "little") + bytes([command, options]) + length + payload
