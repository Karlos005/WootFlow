"""Vectors computed by hand from the Wootility encoder (see docs/wooting-hid-protocol.md)."""
import pytest

from core import wooting_protocol as wp


def test_key_index_packs_row_and_column():
    assert wp.key_index(0, 1) == 0x01
    assert wp.key_index(2, 3) == 0x43
    with pytest.raises(ValueError):
        wp.key_index(6, 0)
    with pytest.raises(ValueError):
        wp.key_index(5, 31)  # collides with the "no key" sentinel


def test_mm_to_raw8_uses_javascript_rounding():
    assert wp.mm_to_raw8(4.0) == 255
    assert wp.mm_to_raw8(2.0) == 128  # 127.5 rounds up like Math.round
    assert wp.mm_to_raw8(9.0) == 255  # clamped
    assert wp.mm_to_raw8(0.0) == 0


def test_14bit_encoding_sets_marker_bit():
    assert wp.encode_value(4.0, wp.FORMAT_14BIT) == 16383 | 0x4000


def test_actuation_partial_8bit_bytes():
    # entry = 128 << 8 | 0x01 = 0x8001 -> varint 81 80 02, unpacked field 1
    assert wp.encode_actuation_partial({(0, 1): 2.0}).hex() == "120408818002"


def test_actuation_partial_14bit_uses_encoded_arm():
    out = wp.encode_actuation_partial({(0, 1): 4.0}, wp.FORMAT_14BIT)
    assert out[0] == (4 << 3 | 2)  # field 4, length-delimited


def test_update_packet_legacy_framing():
    payload = wp.encode_actuation_partial({(0, 1): 2.0})
    pkt = wp.update_packet(wp.CMD_SET_ACTUATION, payload)
    assert pkt.hex() == "d0da1500" "06" "120408818002"


def test_update_packet_multi_uses_two_byte_length_and_save_flag():
    pkt = wp.update_packet(wp.CMD_SET_ACTUATION, b"\x01", save=True, profile_index=2, magic=wp.MAGIC_MULTI)
    assert pkt.hex() == "d1da15" "05" "0100" "01"  # options = 1 | 2<<1 = 5


def test_query_packet_without_profile_uses_ffff():
    assert wp.query_packet(wp.CMD_GET_ACTUATION).hex() == "d0da31ffff0000"
    assert wp.query_packet(wp.CMD_GET_ACTUATION, 3).hex() == "d0da3103000000"


def test_full_rapid_trigger_group_encoding():
    out = wp.encode_full_rapid_trigger(
        [{"keys": [(0, 1)], "sensitivity_mm": 0.4, "secondary_sensitivity_mm": 1.0, "strict_actuation_range": False}]
    )
    # group: keys=0x01, config{primary=round(0.4/4*255)=26, secondary=64, continuous=1}
    cfg = bytes([0x08, 26, 0x10, 64, 0x18, 1])
    group = bytes([0x08, 0x01, 0x12, len(cfg)]) + cfg
    assert out == bytes([0x0A, len(group)]) + group


def test_disabled_group_uses_enabled_arm():
    out = wp.encode_full_rapid_trigger([{"keys": [(0, 1)], "enabled": False}])
    assert out == bytes([0x0A, 4, 0x08, 0x01, 0x18, 0x00])
