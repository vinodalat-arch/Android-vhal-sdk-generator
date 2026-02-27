"""Data models for Android VehicleProperty mappings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .aosp_enums import (
    VehicleArea,
    VehiclePropertyAccess,
    VehiclePropertyChangeMode,
    VehiclePropertyGroup,
    VehiclePropertyType,
)


@dataclass
class PropertyConfig:
    """Configuration for an AOSP VehicleProperty."""
    property_id: int
    access: VehiclePropertyAccess
    change_mode: VehiclePropertyChangeMode
    area_configs: list[AreaConfig] = field(default_factory=list)
    comment: str = ""

    @property
    def property_id_hex(self) -> str:
        return f"0x{self.property_id:08X}"


@dataclass
class AreaConfig:
    area_id: int = 0
    min_int32_value: int = 0
    max_int32_value: int = 0
    min_float_value: float = 0.0
    max_float_value: float = 0.0


@dataclass
class PropertyMapping:
    """Maps a FLYNC signal to an Android VehicleProperty."""
    signal_name: str
    pdu_name: str
    property_id: int
    area_id: int = 0
    access: VehiclePropertyAccess = VehiclePropertyAccess.READ
    change_mode: VehiclePropertyChangeMode = VehiclePropertyChangeMode.ON_CHANGE
    property_type: VehiclePropertyType = VehiclePropertyType.INT32
    is_vendor: bool = False
    is_standard: bool = False
    standard_property_name: Optional[str] = None
    # Signal details for code generation
    pdu_id: int = 0
    start_bit: int = 0
    bit_length: int = 0
    bitmask: int = 0
    is_rx: bool = True
    # Value limits (from signal definition)
    lower_limit: float = 0.0
    upper_limit: float = 0.0
    # Value conversion
    scale: float = 1.0
    offset: float = 0.0
    convert_kmh_to_ms: bool = False

    @property
    def property_id_hex(self) -> str:
        return f"0x{self.property_id:08X}"

    @property
    def vendor_constant_name(self) -> str:
        """Generate C++ constant name for vendor properties."""
        if self.is_vendor:
            return f"VENDOR_{self.signal_name.upper()}"
        return self.standard_property_name or self.signal_name.upper()
