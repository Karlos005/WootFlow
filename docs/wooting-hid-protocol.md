# Wooting configuration protocol (actuation / Rapid Trigger)

Derived by static analysis of the Wootility 5.4.2 renderer bundle installed on
this machine. The bundle's string table and arithmetic constants were
decoded offline; the app was never run and no device was contacted.
Implementation: [`core/wooting_protocol.py`](../core/wooting_protocol.py)
(pure encoders, covered by `tests/test_wooting_protocol.py`).

## Confidence

| Item | Status |
| --- | --- |
| Packet framing, command numbers, protobuf schemas, value scaling | **Observed** in code |
| Unit tests | Check the encoder against hand-computed vectors, **not** against a real device |
| Anything marked *unverified* below | **Not tested on hardware** |

## Transport

WebHID in Wootility; a native HID library would use the same reports.

- **Query** — HID *feature report*, 7 bytes: `magic(2 LE) · command(1) · param(4 LE)`.
  `param` for profile commands is `(namespace << 8 | profileIndex) & 0xFFFF`, or `0xFFFF` for "current".
  The reply arrives as an input report; magic is checked and the body follows the header.
- **Update** — HID *output report*: `magic(2 LE) · command(1) · options(1) · length · payload`.
  `options = save(bit 0) | profileIndex(bits 1-5) | namespace(bits 6-7)`.
  Length is 1 byte for magic `0xDAD0`, 2 bytes LE for `0xDAD1`.
- **Magic words:** `0xDAD0` (56016) legacy interfaces, `0xDAD1` (56017) when the first HID collection has usage page `0xFF55`.
- **Report ID / padding (rev 3):** payload ≤32 → ID 1 (32 B), ≤62 → 2, ≤254 → 3, ≤510 → 4, ≤1022 → 5, ≤2046 → 6. Older revisions pad to 128/256 bytes or chunk by 64.
- `save=false` writes without persisting to flash (used for live preview).

## Commands

| Command | ID | Message |
| --- | --- | --- |
| set actuation | 21 | `KeyMMPropertyProfile` |
| set per-key Rapid Trigger switch | 25 | `KeyPropertyProfile` |
| set full Rapid Trigger | 29 | `RapidTriggerProfile` |
| get analog values | 20 | `MatrixBytes` |
| get actuation / RT / full RT | 49 / 54 / 61 | same as setters |
| activate profile / get current profile index | 23 / 11 | – |

(`set*` IDs and `get*` IDs are separate numbering; setters travel as output reports.)

## Messages (field numbers)

- `KeyMMPropertyProfile` — oneof `full`=1 (`MatrixBytes`), `partial`=2, `fullEncoded`=3 (`MatrixMMEncoded`), `partialEncoded`=4.
- `PartialKeyPropertiesProfile` / `...MMEncoded...` — field 1, **unpacked** repeated `uint32`.
  8-bit entry: `value << 8 | keyIndex`; 14-bit entry: `value << 16 | keyIndex`.
- `MatrixBytes` — field 1 repeated `MatrixBytesRow { bytes values = 1 }`. `MatrixMMRow` — packed `uint32`.
- `KeyPropertyProfile` — oneof `full`=1, `partial`=2. Per-key RT value: `2` on, `1` off, `0` inherit.
- `RapidTriggerProfile` — field 1 repeated `RapidTriggerConfigGroup`:
  `keys`=1 (unpacked `uint32`), oneof `config`=2 (`RapidTriggerConfig`) | `enabled`=3 (`bool`).
- `RapidTriggerConfig` — `primarySensitivity`=1, `secondarySensitivity`=2 (optional), `continuousMode`=3 (optional, `= !strictActuationRange`).

Wootility switches to a full matrix when 50 or more keys change.

## Encoding

- `keyIndex = (row & 7) << 5 | (col & 31)`; `row 5, col 31` means "no key".
- Hall-effect travel: raw `0..255` = `0..4.0 mm`. `raw = round(mm / 4 * 255)`; minimum accepted raw is 7 (about 0.11 mm).
- 8-bit format sends `raw`; 14-bit format sends `round(raw * 16383 / 255) & 0x3FFF | 0x4000`.
- Rapid Trigger sensitivities use the same value encoding as actuation.

## Not verified (needs the keyboard)

1. **Matrix origin.** Wootility addresses keys as `(rowNr, colNr)` in its own matrix; WootFlow's RGB grid is 6×21 with rows from 1. The mapping must be measured with command 20 (press a key, see which cell moves) before any write.
2. **Which interface/format a 60HE exposes** (magic, report ID, 8- vs 14-bit, simple vs full RT). Wootility chooses from device capabilities read at connect time.
3. **Primary vs secondary sensitivity direction** (which is up, which is down) — not stated in the code paths read.
4. **Whether writes work while Wootility is closed**, and whether another HID client can open the config interface alongside the Wooting SDK.
5. Behaviour of `save=false` on this firmware.

## Safety plan before the first write

Read first, write second: use the query commands to snapshot the current actuation and Rapid Trigger profiles, write with `save=false` to a profile that can be reverted, and only persist after confirming the readback.
