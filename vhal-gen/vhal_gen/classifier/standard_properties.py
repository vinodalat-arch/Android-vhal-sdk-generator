"""AOSP standard VehicleProperty IDs (Android 14).

This module provides a static lookup table of well-known VehicleProperty IDs
defined in ``android.hardware.automotive.vehicle.VehicleProperty``.  The
classifier uses this table to resolve standard property names (e.g.
``HEADLIGHTS_STATE``) to their canonical 32-bit property IDs so that
exact-match rules can reference properties by name rather than raw hex
values.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Standard property IDs
# ---------------------------------------------------------------------------
# Each ID encodes VehiclePropertyGroup, VehicleArea, VehiclePropertyType, and
# a unique property index according to the AOSP VHAL specification.
# ---------------------------------------------------------------------------

STANDARD_PROPERTIES: dict[str, int] = {
    # --- Exterior lights ---------------------------------------------------
    "HEADLIGHTS_STATE": 0x0E010A00,
    "HEADLIGHTS_SWITCH": 0x0E010A01,
    "HIGH_BEAM_LIGHTS_STATE": 0x0E010A02,
    "HIGH_BEAM_LIGHTS_SWITCH": 0x0E010A03,
    "TURN_SIGNAL_STATE": 0x0E010A04,
    "HAZARD_LIGHTS_STATE": 0x0E010A05,
    "HAZARD_LIGHTS_SWITCH": 0x0E010A06,
    # --- Door --------------------------------------------------------------
    "DOOR_LOCK": 0x0B010B00,
    # --- Driving / speed ---------------------------------------------------
    "PERF_VEHICLE_SPEED": 0x11600207,
    # --- Display / environment ---------------------------------------------
    "NIGHT_MODE": 0x11200407,
}


def get_property_id(property_name: str) -> int | None:
    """Return the standard property ID for *property_name*, or ``None``."""
    return STANDARD_PROPERTIES.get(property_name)
