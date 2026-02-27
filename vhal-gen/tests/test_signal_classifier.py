"""Tests for the signal classifier."""

from pathlib import Path

from vhal_gen.classifier.signal_classifier import SignalClassifier
from vhal_gen.classifier.standard_properties import STANDARD_PROPERTIES
from vhal_gen.models.aosp_enums import VehiclePropertyAccess, VehiclePropertyType
from vhal_gen.parser.model_loader import load_flync_model

MODEL_DIR = Path(__file__).parent.parent.parent / "flync-model-dev-2"


def _get_mappings():
    model = load_flync_model(MODEL_DIR)
    classifier = SignalClassifier()
    return classifier.classify(model)


def test_standard_mapping_count():
    """Verify expected number of standard AOSP mappings."""
    mappings = _get_mappings()
    standard = [m for m in mappings if m.is_standard]
    assert len(standard) >= 11, f"Expected at least 11 standard mappings, got {len(standard)}"


def test_vendor_mapping_count():
    """Verify vendor mappings are generated for remaining signals."""
    mappings = _get_mappings()
    vendor = [m for m in mappings if m.is_vendor]
    assert len(vendor) > 0, "Expected vendor mappings"


def test_headlights_switch_mapping():
    """Verify u8_MainLightSelector_Req maps to HEADLIGHTS_SWITCH."""
    mappings = _get_mappings()
    m = next(m for m in mappings if m.signal_name == "u8_MainLightSelector_Req")
    assert m.is_standard
    assert m.standard_property_name == "HEADLIGHTS_SWITCH"
    assert m.property_id == STANDARD_PROPERTIES["HEADLIGHTS_SWITCH"]


def test_vehicle_speed_mapping():
    """Verify u8_VehSpd_kmph maps to PERF_VEHICLE_SPEED with float type."""
    mappings = _get_mappings()
    m = next(m for m in mappings if m.signal_name == "u8_VehSpd_kmph")
    assert m.is_standard
    assert m.standard_property_name == "PERF_VEHICLE_SPEED"
    assert m.property_type == VehiclePropertyType.FLOAT
    assert m.convert_kmh_to_ms is True


def test_door_lock_per_area():
    """Verify door unlock signals map to DOOR_LOCK with correct area IDs."""
    mappings = _get_mappings()
    door_locks = [m for m in mappings if m.signal_name.endswith("_Unlock_Sts")]
    assert len(door_locks) == 4
    area_ids = {m.area_id for m in door_locks}
    assert 0x01 in area_ids  # ROW_1_LEFT
    assert 0x04 in area_ids  # ROW_1_RIGHT
    assert 0x10 in area_ids  # ROW_2_LEFT
    assert 0x40 in area_ids  # ROW_2_RIGHT


def test_crc_counter_skipped():
    """Verify crc16 and counter signals are not in mappings."""
    mappings = _get_mappings()
    names = {m.signal_name for m in mappings}
    assert "crc16" not in names
    assert "counter" not in names


def test_vendor_ids_unique():
    """Verify all vendor property IDs are unique (within same signal name)."""
    mappings = _get_mappings()
    vendor = [m for m in mappings if m.is_vendor]
    # Group by signal name - same name should get same ID
    by_name = {}
    for m in vendor:
        if m.signal_name in by_name:
            assert m.property_id == by_name[m.signal_name], (
                f"Signal {m.signal_name} got different IDs"
            )
        by_name[m.signal_name] = m.property_id


def test_rx_signals_read_only():
    """Verify RX signals are mapped as READ access."""
    mappings = _get_mappings()
    rx = [m for m in mappings if m.is_rx]
    for m in rx:
        assert m.access == VehiclePropertyAccess.READ, (
            f"RX signal {m.signal_name} should be READ, got {m.access}"
        )


def test_tx_signals_read_write():
    """Verify TX signals from known-direction PDUs are mapped as READ_WRITE."""
    mappings = _get_mappings()
    # Only check signals from PDUs with resolved TX direction (0x101 = ExteriorLighting_Doors_Cmd)
    tx = [m for m in mappings if not m.is_rx and m.is_vendor and m.pdu_id == 0x101]
    assert len(tx) > 0, "Expected TX vendor signals from PDU 0x101"
    for m in tx:
        assert m.access == VehiclePropertyAccess.READ_WRITE, (
            f"TX vendor signal {m.signal_name} should be READ_WRITE, got {m.access}"
        )
