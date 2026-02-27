"""Tests for the PDU parser."""

from pathlib import Path

from vhal_gen.parser.pdu_parser import parse_pdu_directory, parse_pdu_file

PDU_DIR = Path(__file__).parent.parent.parent / "flync-model-dev-2" / "flync-model-dev" / "general" / "channels" / "pdus"


def test_parse_exterior_lighting_req():
    """Verify ExteriorLighting_Doors_Req PDU parses correctly."""
    pdu = parse_pdu_file(PDU_DIR / "ExteriorLighting_Doors_Req.flync.yaml")
    assert pdu.name == "ExteriorLighting_Doors_Req"
    assert pdu.pdu_id == 0x401
    assert pdu.length == 8
    assert len(pdu.signals) == 15


def test_parse_exterior_lighting_cmd():
    """Verify ExteriorLighting_Doors_Cmd PDU parses correctly."""
    pdu = parse_pdu_file(PDU_DIR / "ExteriorLighting_Doors_Cmd.flync.yaml")
    assert pdu.name == "ExteriorLighting_Doors_Cmd"
    assert pdu.pdu_id == 0x101
    assert pdu.length == 8
    assert len(pdu.signals) == 20


def test_start_bit_accumulation_req():
    """Verify start_bit computation matches ComConfig.cpp reference for 0x401."""
    pdu = parse_pdu_file(PDU_DIR / "ExteriorLighting_Doors_Req.flync.yaml")
    # Reference from ComConfig.cpp ComRxSignalInfo_0x401
    expected = [
        ("u8_TurnLight_req", 0, 3),
        ("bo_Crash_Detection_sts", 3, 1),
        ("u8_PowerModeStatus", 4, 2),
        ("bo_RKE_Authentication_Status", 6, 1),
        ("bo_BattVg_AbvTH", 7, 1),
        ("u8_ALS_Data", 8, 2),
        ("u8_Beam_Req", 10, 2),
        ("u8_MainLightSelector_Req", 12, 2),
        ("u8_HazardLight_req", 14, 2),
        ("bo_ChldLck_DrSW", 16, 2),
        ("bo_DoorLock_Sw", 18, 2),
        ("bo_DoorKey_req", 20, 2),
        ("u8_RainLightSensor_Data", 22, 2),
        ("u8_VehSpd_kmph", 24, 8),
        ("u8_BlinkFreq_Req", 32, 8),
    ]
    for i, (name, start_bit, bit_length) in enumerate(expected):
        sig = pdu.signals[i]
        assert sig.name == name, f"Signal {i}: expected {name}, got {sig.name}"
        assert sig.start_bit == start_bit, f"Signal {name}: expected start_bit={start_bit}, got {sig.start_bit}"
        assert sig.bit_length == bit_length, f"Signal {name}: expected bit_length={bit_length}, got {sig.bit_length}"


def test_start_bit_accumulation_cmd():
    """Verify start_bit computation matches ComConfig.cpp reference for 0x101."""
    pdu = parse_pdu_file(PDU_DIR / "ExteriorLighting_Doors_Cmd.flync.yaml")
    # First few from ComConfig.cpp ComTxSignalInfo_0x101
    expected_starts = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22]
    for i, expected_start in enumerate(expected_starts):
        sig = pdu.signals[i]
        assert sig.start_bit == expected_start, (
            f"Signal {sig.name} (idx {i}): expected start_bit={expected_start}, got {sig.start_bit}"
        )


def test_bitmask_computation():
    """Verify bitmask is correctly computed from bit_length."""
    pdu = parse_pdu_file(PDU_DIR / "ExteriorLighting_Doors_Req.flync.yaml")
    # 3-bit signal → mask 0x07
    assert pdu.signals[0].bitmask == 0x07
    # 1-bit signal → mask 0x01
    assert pdu.signals[1].bitmask == 0x01
    # 2-bit signal → mask 0x03
    assert pdu.signals[2].bitmask == 0x03
    # 8-bit signal → mask 0xFF
    assert pdu.signals[13].bitmask == 0xFF


def test_value_table_parsed():
    """Verify value_table entries are correctly parsed."""
    pdu = parse_pdu_file(PDU_DIR / "ExteriorLighting_Doors_Req.flync.yaml")
    turn_signal = pdu.signals[0]
    assert len(turn_signal.value_table) == 6
    assert turn_signal.value_table[0].num_value == 0
    assert turn_signal.value_table[0].description == "IL_IDLE"
    assert turn_signal.value_table[1].description == "LEFT"


def test_parse_pdu_directory():
    """Verify all PDU files in directory are parsed."""
    pdus = parse_pdu_directory(PDU_DIR)
    assert len(pdus) == 10
    assert "ExteriorLighting_Doors_Req" in pdus
    assert "ExteriorLighting_Doors_Cmd" in pdus


def test_signal_name_stripping():
    """Verify signal names with whitespace are stripped."""
    pdu = parse_pdu_file(PDU_DIR / "ExteriorLighting_Doors_Req.flync.yaml")
    # u8_HazardLight_req has a leading space in YAML
    hazard = next(s for s in pdu.signals if "HazardLight" in s.name)
    assert hazard.name == "u8_HazardLight_req"
    assert not hazard.name.startswith(" ")
