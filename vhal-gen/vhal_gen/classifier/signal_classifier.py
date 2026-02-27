"""Signal classifier -- maps FLYNC signals to Android VehicleProperty IDs.

The classification pipeline is:

1. **Exact match** -- the signal name is looked up in
   :data:`mapping_rules.EXACT_MATCH_RULES`.  If found the standard AOSP
   property ID is used directly from
   :data:`standard_properties.STANDARD_PROPERTIES`.
2. **Vendor fallback** -- if no exact match exists a unique vendor property
   ID is generated via :class:`vendor_id_allocator.VendorIdAllocator`.

Signals whose name is ``"crc16"`` or ``"counter"`` are silently skipped
because they are transport-layer housekeeping fields that have no
corresponding vehicle property.
"""

from __future__ import annotations

import logging
from typing import Sequence

from ..models.aosp_enums import (
    VehicleArea,
    VehiclePropertyAccess,
    VehiclePropertyChangeMode,
    VehiclePropertyType,
)
from ..models.signal import Direction, FlyncModel, PDU, Signal
from ..models.vehicle_property import PropertyMapping
from .mapping_rules import EXACT_MATCH_RULES
from .standard_properties import STANDARD_PROPERTIES
from .vendor_id_allocator import VendorIdAllocator

logger = logging.getLogger(__name__)

# Signal names that should never be exposed as vehicle properties.
_SKIP_SIGNALS: frozenset[str] = frozenset({"crc16", "counter"})


class SignalClassifier:
    """Classify every signal in a :class:`FlyncModel` as either a standard
    AOSP property or a vendor property and return a list of
    :class:`PropertyMapping` instances ready for code generation.

    Parameters
    ----------
    vendor_start_counter:
        Passed through to :class:`VendorIdAllocator`.
    """

    def __init__(self, vendor_start_counter: int = 0x0101) -> None:
        self._vendor_allocator = VendorIdAllocator(
            start_counter=vendor_start_counter,
        )

    # -- public API ---------------------------------------------------------

    def classify(self, model: FlyncModel) -> list[PropertyMapping]:
        """Classify all signals in *model* to VehicleProperty mappings.

        Parameters
        ----------
        model:
            A fully parsed FLYNC model whose ``pdus`` dict contains the
            signals to classify.

        Returns
        -------
        list[PropertyMapping]
            One mapping per non-skipped signal, in PDU iteration order.
        """
        mappings: list[PropertyMapping] = []

        for pdu_name, pdu in model.pdus.items():
            for signal in pdu.signals:
                if signal.name in _SKIP_SIGNALS:
                    logger.debug(
                        "Skipping housekeeping signal %r in PDU %r",
                        signal.name,
                        pdu_name,
                    )
                    continue

                mapping = self._classify_signal(signal, pdu)
                mappings.append(mapping)

        logger.info(
            "Classified %d signals (%d standard, %d vendor)",
            len(mappings),
            sum(1 for m in mappings if m.is_standard),
            sum(1 for m in mappings if m.is_vendor),
        )
        return mappings

    # -- internals ----------------------------------------------------------

    def _classify_signal(self, signal: Signal, pdu: PDU) -> PropertyMapping:
        """Classify a single signal.

        First attempts an exact-match lookup; falls back to vendor ID
        allocation when no rule matches.
        """
        rule = EXACT_MATCH_RULES.get(signal.name)

        if rule is not None:
            return self._build_standard_mapping(signal, pdu, rule)

        return self._build_vendor_mapping(signal, pdu)

    # -- standard (exact match) ---------------------------------------------

    def _build_standard_mapping(
        self,
        signal: Signal,
        pdu: PDU,
        rule: dict,
    ) -> PropertyMapping:
        """Build a :class:`PropertyMapping` for a known AOSP property."""
        property_name: str = rule["property_name"]
        property_id = STANDARD_PROPERTIES[property_name]

        area: VehicleArea = rule["area"]
        area_id: int = rule.get("area_id", 0)
        prop_type: VehiclePropertyType = rule["type"]
        access: VehiclePropertyAccess = rule["access"]
        change_mode: VehiclePropertyChangeMode = rule["change_mode"]
        convert_kmh_to_ms: bool = rule.get("convert_kmh_to_ms", False)

        logger.debug(
            "Exact match: signal %r -> %s (0x%08X)",
            signal.name,
            property_name,
            property_id,
        )

        return PropertyMapping(
            signal_name=signal.name,
            pdu_name=pdu.name,
            property_id=property_id,
            area_id=area_id,
            access=access,
            change_mode=change_mode,
            property_type=prop_type,
            is_vendor=False,
            is_standard=True,
            standard_property_name=property_name,
            pdu_id=pdu.pdu_id,
            start_bit=signal.start_bit,
            bit_length=signal.bit_length,
            bitmask=signal.bitmask,
            is_rx=(pdu.direction == Direction.RX),
            lower_limit=signal.lower_limit,
            upper_limit=signal.upper_limit,
            scale=signal.scale,
            offset=signal.offset,
            convert_kmh_to_ms=convert_kmh_to_ms,
        )

    # -- vendor (fallback) --------------------------------------------------

    def _build_vendor_mapping(
        self,
        signal: Signal,
        pdu: PDU,
    ) -> PropertyMapping:
        """Build a :class:`PropertyMapping` backed by a vendor property ID."""
        vendor_id = self._vendor_allocator.allocate(
            signal.name,
            signal.base_data_type,
        )

        # Infer a sensible VehiclePropertyType from the FLYNC base data type.
        prop_type = self._infer_property_type(signal.base_data_type)

        # Infer access from PDU direction: RX signals are read-only from the
        # framework's perspective; TX signals are writable.
        access = self._infer_access(pdu.direction)

        logger.debug(
            "Vendor fallback: signal %r -> 0x%08X",
            signal.name,
            vendor_id,
        )

        return PropertyMapping(
            signal_name=signal.name,
            pdu_name=pdu.name,
            property_id=vendor_id,
            area_id=0,
            access=access,
            change_mode=VehiclePropertyChangeMode.ON_CHANGE,
            property_type=prop_type,
            is_vendor=True,
            is_standard=False,
            standard_property_name=None,
            pdu_id=pdu.pdu_id,
            start_bit=signal.start_bit,
            bit_length=signal.bit_length,
            bitmask=signal.bitmask,
            is_rx=(pdu.direction == Direction.RX),
            lower_limit=signal.lower_limit,
            upper_limit=signal.upper_limit,
            scale=signal.scale,
            offset=signal.offset,
            convert_kmh_to_ms=False,
        )

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _infer_property_type(base_data_type: str) -> VehiclePropertyType:
        """Map a FLYNC ``base_data_type`` to a ``VehiclePropertyType``."""
        mapping: dict[str, VehiclePropertyType] = {
            "bool": VehiclePropertyType.BOOLEAN,
            "uint8": VehiclePropertyType.INT32,
            "uint16": VehiclePropertyType.INT32,
            "uint32": VehiclePropertyType.INT32,
            "int8": VehiclePropertyType.INT32,
            "int16": VehiclePropertyType.INT32,
            "int32": VehiclePropertyType.INT32,
            "float": VehiclePropertyType.FLOAT,
            "float32": VehiclePropertyType.FLOAT,
            "float64": VehiclePropertyType.FLOAT,
        }
        return mapping.get(base_data_type, VehiclePropertyType.INT32)

    @staticmethod
    def _infer_access(direction: Direction) -> VehiclePropertyAccess:
        """Derive ``VehiclePropertyAccess`` from the PDU direction.

        * **RX** PDUs carry data *received* by the ECU and are therefore
          *read-only* from Android's point of view.
        * **TX** PDUs carry data *sent* by Android and are *write-only*.
        * When the direction is unknown, default to ``READ``.
        """
        if direction == Direction.TX:
            return VehiclePropertyAccess.READ_WRITE
        # RX and UNKNOWN both default to READ.
        return VehiclePropertyAccess.READ
