"""Exact-match mapping rules from FLYNC signal names to AOSP VehicleProperty
configurations.

Each entry in :data:`EXACT_MATCH_RULES` maps a *signal name* (as it appears
in the FLYNC model) to a dictionary describing the target AOSP property.
The dictionary **must** contain at least:

* ``property_name`` -- key into :data:`standard_properties.STANDARD_PROPERTIES`
* ``area``          -- :class:`VehicleArea` enum member
* ``type``          -- :class:`VehiclePropertyType` enum member
* ``access``        -- :class:`VehiclePropertyAccess` enum member
* ``change_mode``   -- :class:`VehiclePropertyChangeMode` enum member

Optional keys:

* ``area_id``            -- concrete area bitmask (defaults to ``0`` for GLOBAL)
* ``convert_kmh_to_ms``  -- if ``True`` the generated HAL code must convert
                            km/h to m/s at runtime
"""

from __future__ import annotations

from ..models.aosp_enums import (
    VehicleArea,
    VehiclePropertyAccess,
    VehiclePropertyChangeMode,
    VehiclePropertyType,
)

# ---------------------------------------------------------------------------
# Exact-match rules
# ---------------------------------------------------------------------------
# Keys   : FLYNC signal name (case-sensitive, must match exactly)
# Values : property configuration dictionaries consumed by SignalClassifier
# ---------------------------------------------------------------------------

EXACT_MATCH_RULES: dict[str, dict] = {
    # -----------------------------------------------------------------------
    # Exterior lights
    # -----------------------------------------------------------------------
    "u8_MainLightSelector_Req": {
        "property_name": "HEADLIGHTS_SWITCH",
        "area": VehicleArea.GLOBAL,
        "type": VehiclePropertyType.INT32,
        "access": VehiclePropertyAccess.READ,
        "change_mode": VehiclePropertyChangeMode.ON_CHANGE,
    },
    "u8_MainLightSelector_Status": {
        "property_name": "HEADLIGHTS_STATE",
        "area": VehicleArea.GLOBAL,
        "type": VehiclePropertyType.INT32,
        "access": VehiclePropertyAccess.READ,
        "change_mode": VehiclePropertyChangeMode.ON_CHANGE,
    },
    "u8_HighBeam": {
        "property_name": "HIGH_BEAM_LIGHTS_STATE",
        "area": VehicleArea.GLOBAL,
        "type": VehiclePropertyType.INT32,
        "access": VehiclePropertyAccess.READ,
        "change_mode": VehiclePropertyChangeMode.ON_CHANGE,
    },
    "u8_Beam_Req": {
        "property_name": "HIGH_BEAM_LIGHTS_SWITCH",
        "area": VehicleArea.GLOBAL,
        "type": VehiclePropertyType.INT32,
        "access": VehiclePropertyAccess.READ,
        "change_mode": VehiclePropertyChangeMode.ON_CHANGE,
    },
    "u8_TurnLight_req": {
        "property_name": "TURN_SIGNAL_STATE",
        "area": VehicleArea.GLOBAL,
        "type": VehiclePropertyType.INT32,
        "access": VehiclePropertyAccess.READ,
        "change_mode": VehiclePropertyChangeMode.ON_CHANGE,
    },
    "u8_HazardLight_req": {
        "property_name": "HAZARD_LIGHTS_SWITCH",
        "area": VehicleArea.GLOBAL,
        "type": VehiclePropertyType.INT32,
        "access": VehiclePropertyAccess.READ,
        "change_mode": VehiclePropertyChangeMode.ON_CHANGE,
    },
    "bo_HazardLight_cmd": {
        "property_name": "HAZARD_LIGHTS_STATE",
        "area": VehicleArea.GLOBAL,
        "type": VehiclePropertyType.BOOLEAN,
        "access": VehiclePropertyAccess.READ,
        "change_mode": VehiclePropertyChangeMode.ON_CHANGE,
    },
    # -----------------------------------------------------------------------
    # Door locks
    # -----------------------------------------------------------------------
    "bo_DoorLock_Sw": {
        "property_name": "DOOR_LOCK",
        "area": VehicleArea.GLOBAL,
        "type": VehiclePropertyType.BOOLEAN,
        "access": VehiclePropertyAccess.READ,
        "change_mode": VehiclePropertyChangeMode.ON_CHANGE,
    },
    "bo_FR_Unlock_Sts": {
        "property_name": "DOOR_LOCK",
        "area_id": 0x00000004,  # ROW_1_RIGHT
        "area": VehicleArea.DOOR,
        "type": VehiclePropertyType.BOOLEAN,
        "access": VehiclePropertyAccess.READ,
        "change_mode": VehiclePropertyChangeMode.ON_CHANGE,
    },
    "bo_FL_Unlock_Sts": {
        "property_name": "DOOR_LOCK",
        "area_id": 0x00000001,  # ROW_1_LEFT
        "area": VehicleArea.DOOR,
        "type": VehiclePropertyType.BOOLEAN,
        "access": VehiclePropertyAccess.READ,
        "change_mode": VehiclePropertyChangeMode.ON_CHANGE,
    },
    "bo_RR_Unlock_Sts": {
        "property_name": "DOOR_LOCK",
        "area_id": 0x00000040,  # ROW_2_RIGHT
        "area": VehicleArea.DOOR,
        "type": VehiclePropertyType.BOOLEAN,
        "access": VehiclePropertyAccess.READ,
        "change_mode": VehiclePropertyChangeMode.ON_CHANGE,
    },
    "bo_RL_Unlock_Sts": {
        "property_name": "DOOR_LOCK",
        "area_id": 0x00000010,  # ROW_2_LEFT
        "area": VehicleArea.DOOR,
        "type": VehiclePropertyType.BOOLEAN,
        "access": VehiclePropertyAccess.READ,
        "change_mode": VehiclePropertyChangeMode.ON_CHANGE,
    },
    # -----------------------------------------------------------------------
    # Vehicle speed
    # -----------------------------------------------------------------------
    "u8_VehSpd_kmph": {
        "property_name": "PERF_VEHICLE_SPEED",
        "area": VehicleArea.GLOBAL,
        "type": VehiclePropertyType.FLOAT,
        "access": VehiclePropertyAccess.READ,
        "change_mode": VehiclePropertyChangeMode.CONTINUOUS,
        "convert_kmh_to_ms": True,
    },
    # -----------------------------------------------------------------------
    # Ambient light / night mode
    # -----------------------------------------------------------------------
    "u8_ALS_Data": {
        "property_name": "NIGHT_MODE",
        "area": VehicleArea.GLOBAL,
        "type": VehiclePropertyType.BOOLEAN,
        "access": VehiclePropertyAccess.READ,
        "change_mode": VehiclePropertyChangeMode.ON_CHANGE,
    },
}
