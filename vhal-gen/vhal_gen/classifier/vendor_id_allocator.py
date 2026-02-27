"""Vendor VehicleProperty ID allocator.

Signals that do not match any AOSP standard property are assigned a
*vendor* property ID.  The 32-bit ID is composed by OR-ing four fields
together::

    VehiclePropertyGroup.VENDOR | VehicleArea | VehiclePropertyType | counter

The allocator keeps an internal counter that starts at ``0x0101`` (by
default) and increments by one for every allocation.  Each signal receives
a unique counter value so that generated IDs never collide within a single
classification run.
"""

from __future__ import annotations

import logging

from ..models.aosp_enums import (
    VehicleArea,
    VehiclePropertyGroup,
    VehiclePropertyType,
)

logger = logging.getLogger(__name__)

# Mapping from FLYNC ``base_data_type`` strings to VehiclePropertyType.
_DATA_TYPE_MAP: dict[str, VehiclePropertyType] = {
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

# Upper bound (exclusive) for the 16-bit counter portion of the ID.
_MAX_COUNTER = 0xFFFF


class VendorIdAllocator:
    """Deterministic allocator for vendor VehicleProperty IDs.

    Parameters
    ----------
    start_counter:
        First counter value to use.  Defaults to ``0x0101`` to leave the
        low range free for future reserved IDs.
    """

    def __init__(self, start_counter: int = 0x0101) -> None:
        if not (0 <= start_counter <= _MAX_COUNTER):
            raise ValueError(
                f"start_counter must be in [0, {_MAX_COUNTER:#06x}], "
                f"got {start_counter:#06x}"
            )
        self._counter: int = start_counter
        self._allocated: dict[str, int] = {}

    # -- public API ---------------------------------------------------------

    def allocate(self, signal_name: str, base_data_type: str) -> int:
        """Generate a vendor property ID for *signal_name*.

        If the same *signal_name* is allocated more than once the
        previously assigned ID is returned (idempotent).

        Parameters
        ----------
        signal_name:
            The FLYNC signal name (used for deduplication and logging).
        base_data_type:
            The FLYNC ``base_data_type`` string (e.g. ``"bool"``,
            ``"uint8"``).  This determines the ``VehiclePropertyType``
            component of the ID.

        Returns
        -------
        int
            A 32-bit vendor property ID.

        Raises
        ------
        RuntimeError
            If the internal counter overflows the 16-bit range.
        """
        # Return cached ID if this signal was already allocated.
        if signal_name in self._allocated:
            return self._allocated[signal_name]

        if self._counter > _MAX_COUNTER:
            raise RuntimeError(
                f"Vendor property ID counter overflow: attempted to allocate "
                f"ID #{self._counter:#06x} which exceeds the 16-bit limit."
            )

        prop_type = _DATA_TYPE_MAP.get(base_data_type, VehiclePropertyType.INT32)

        vendor_id: int = (
            VehiclePropertyGroup.VENDOR
            | VehicleArea.GLOBAL
            | prop_type
            | self._counter
        )

        self._allocated[signal_name] = vendor_id
        logger.debug(
            "Allocated vendor ID 0x%08X for signal %r (type=%s, counter=%d)",
            vendor_id,
            signal_name,
            prop_type.name,
            self._counter,
        )
        self._counter += 1
        return vendor_id

    # -- introspection ------------------------------------------------------

    @property
    def allocated_count(self) -> int:
        """Number of unique vendor IDs allocated so far."""
        return len(self._allocated)

    @property
    def next_counter(self) -> int:
        """The counter value that will be used for the next allocation."""
        return self._counter

    def reset(self, start_counter: int = 0x0101) -> None:
        """Reset the allocator to its initial state.

        This is mainly useful in test scenarios.
        """
        self._counter = start_counter
        self._allocated.clear()
