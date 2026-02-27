"""Integration test: full pipeline from YAML to generated output."""

import json
import tempfile
from pathlib import Path

from vhal_gen.classifier.signal_classifier import SignalClassifier
from vhal_gen.generator.generator_engine import GeneratorEngine
from vhal_gen.parser.model_loader import load_flync_model

MODEL_DIR = Path(__file__).parent.parent.parent / "flync-model-dev-2"


def test_full_pipeline():
    """End-to-end test: parse → classify → generate."""
    # 1. Parse
    model = load_flync_model(MODEL_DIR)
    assert len(model.pdus) == 10
    assert sum(len(p.signals) for p in model.pdus.values()) == 49

    # 2. Classify
    classifier = SignalClassifier()
    mappings = classifier.classify(model)
    assert len(mappings) > 30  # 43 signals minus crc16/counter skips

    # Verify specific mappings
    by_name = {m.signal_name: m for m in mappings}
    assert "u8_TurnLight_req" in by_name
    assert by_name["u8_TurnLight_req"].is_standard
    assert "bo_DRL_cmd" in by_name
    assert by_name["bo_DRL_cmd"].is_vendor

    # Verify SDK function names are populated
    turn_light = by_name["u8_TurnLight_req"]
    assert turn_light.sdk_getter == "get_u8_TurnLight_req"
    assert turn_light.sdk_setter is None  # RX signal

    drl = by_name["bo_DRL_cmd"]
    assert drl.sdk_setter == "set_bo_DRL_cmd"
    assert drl.sdk_getter is None  # TX signal

    # 3. Generate
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = GeneratorEngine(mappings=mappings, model=model)
        generated = engine.generate(Path(tmpdir))
        assert len(generated) == 13

        # Verify JSON (AOSP format with apiVersion wrapper)
        json_raw = json.loads((Path(tmpdir) / "vhal" / "DefaultProperties.json").read_text())
        assert json_raw["apiVersion"] == 1
        json_data = json_raw["properties"]
        assert len(json_data) == len(mappings)

        # Verify VendorProperties.h has pragma once
        vendor_h = (Path(tmpdir) / "vhal" / "VendorProperties.h").read_text()
        assert "#pragma once" in vendor_h

        # Verify Android.bp has bridge lib, daemon, and SDK sources
        bp = (Path(tmpdir) / "vhal" / "Android.bp").read_text()
        assert "BridgeVehicleHardware" in bp
        assert "flync-daemon" in bp
        assert "@V1" not in bp  # No version-specific references
        assert "sdk/com/src/ComConfig.cpp" in bp
        assert "sdk/app/swc/Read_App_Signal_Data.cpp" in bp

        # Verify daemon uses SDK includes
        daemon_cpp = (Path(tmpdir) / "vhal" / "FlyncDaemon.cpp").read_text()
        assert "Read_App_Signal_Data.h" in daemon_cpp
        assert "Write_App_Signal_Data.h" in daemon_cpp
        assert "extractBits" not in daemon_cpp
        assert "packBits" not in daemon_cpp

        # Verify daemon rc (no --mock flag)
        rc = (Path(tmpdir) / "vhal" / "flync-daemon.rc").read_text()
        assert "flync-daemon" in rc
        assert "--mock" not in rc


def test_signal_bit_positions_match_reference():
    """Cross-check computed bit positions against ComConfig.cpp reference."""
    model = load_flync_model(MODEL_DIR)
    req_pdu = model.pdus["ExteriorLighting_Doors_Req"]

    # Ground truth from ComConfig.cpp ComRxSignalInfo_0x401[15]
    reference = {
        "u8_TurnLight_req": (0, 3, 0x07),
        "bo_Crash_Detection_sts": (3, 1, 0x01),
        "u8_PowerModeStatus": (4, 2, 0x03),
        "bo_RKE_Authentication_Status": (6, 1, 0x01),
        "bo_BattVg_AbvTH": (7, 1, 0x01),
        "u8_ALS_Data": (8, 2, 0x03),
        "u8_Beam_Req": (10, 2, 0x03),
        "u8_MainLightSelector_Req": (12, 2, 0x03),
        "u8_HazardLight_req": (14, 2, 0x03),
        "bo_ChldLck_DrSW": (16, 2, 0x03),
        "bo_DoorLock_Sw": (18, 2, 0x03),
        "bo_DoorKey_req": (20, 2, 0x03),
        "u8_RainLightSensor_Data": (22, 2, 0x03),
        "u8_VehSpd_kmph": (24, 8, 0xFF),
        "u8_BlinkFreq_Req": (32, 8, 0xFF),
    }

    for sig in req_pdu.signals:
        if sig.name in reference:
            expected_start, expected_len, expected_mask = reference[sig.name]
            assert sig.start_bit == expected_start, (
                f"{sig.name}: start_bit mismatch ({sig.start_bit} != {expected_start})"
            )
            assert sig.bit_length == expected_len, (
                f"{sig.name}: bit_length mismatch ({sig.bit_length} != {expected_len})"
            )
            assert sig.bitmask == expected_mask, (
                f"{sig.name}: bitmask mismatch (0x{sig.bitmask:X} != 0x{expected_mask:X})"
            )
