"""Parser for FLYNC channel definition YAML files.

Reads the ``channels.yaml`` file to produce :class:`Channel` objects and
builds a mapping from PDU ID to communication direction (RX / TX) as seen
from the IVI (HPC) perspective.

Direction convention
--------------------
* **RX** -- a vehicle-side ECU (e.g. ``zc_fl_controller``, ``zc_fr_controller``)
  sends *to* ``hpc`` / ``hpc2``.  From the IVI standpoint these are *received*
  signals.
* **TX** -- ``hpc`` or ``hpc2`` sends *to* a vehicle-side ECU (e.g.
  ``zc_fr_controller``).  From the IVI standpoint these are *transmitted*
  signals.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from ..models.signal import Channel, ChannelMessage, Direction

logger = logging.getLogger(__name__)

# ECU identifiers that represent the IVI / head-unit side.
_IVI_SENDERS: frozenset[str] = frozenset({"hpc", "hpc2"})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_hex_id(raw_value: Any) -> int:
    """Parse an ID that may be a hex string (``'0x1401'``) or plain int."""
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, str):
        raw_value = raw_value.strip()
        try:
            return int(raw_value, 16) if raw_value.lower().startswith("0x") else int(raw_value)
        except ValueError:
            raise ValueError(f"Cannot parse hex ID value: {raw_value!r}")
    raise TypeError(f"Unexpected type for ID field: {type(raw_value).__name__} ({raw_value!r})")


def _determine_direction(sender: str, receivers: list[str]) -> Direction:
    """Determine the direction of a message from the IVI perspective.

    Parameters
    ----------
    sender:
        The ECU that originates the message.
    receivers:
        The list of ECUs that consume the message.
    """
    sender_lower = sender.lower()
    receivers_lower = [r.lower() for r in receivers]

    # If the IVI side is the sender --> TX from IVI to vehicle.
    if sender_lower in _IVI_SENDERS:
        return Direction.TX

    # If the IVI side is a receiver --> RX at IVI from vehicle.
    if any(r in _IVI_SENDERS for r in receivers_lower):
        return Direction.RX

    return Direction.UNKNOWN


def _parse_message(raw_msg: dict[str, Any]) -> ChannelMessage:
    """Parse a single message entry within a channel definition."""
    name = str(raw_msg["name"]).strip()
    frame_id = _parse_hex_id(raw_msg["id"])
    protocol = str(raw_msg.get("protocol", ""))
    sender = str(raw_msg.get("sender", "")).strip()
    receivers = [str(r).strip() for r in raw_msg.get("receivers", [])]

    # The PDU reference is nested: pdu.pdu
    pdu_ref_id: int | None = None
    pdu_block = raw_msg.get("pdu")
    if isinstance(pdu_block, dict):
        raw_pdu_id = pdu_block.get("pdu")
        if raw_pdu_id is not None:
            pdu_ref_id = _parse_hex_id(raw_pdu_id)

    return ChannelMessage(
        name=name,
        frame_id=frame_id,
        protocol=protocol,
        sender=sender,
        receivers=receivers,
        pdu_id=pdu_ref_id,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_channels(filepath: Path) -> list[Channel]:
    """Parse a ``channels.yaml`` file and return a list of :class:`Channel`.

    Parameters
    ----------
    filepath:
        Path to the ``channels.yaml`` file.

    Returns
    -------
    list[Channel]
        All parsed channel definitions.

    Raises
    ------
    FileNotFoundError
        If *filepath* does not exist.
    yaml.YAMLError
        If the YAML is malformed.
    """
    filepath = Path(filepath)
    if not filepath.is_file():
        raise FileNotFoundError(f"Channels file not found: {filepath}")

    logger.debug("Parsing channels file: %s", filepath)

    with open(filepath, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if data is None or "channels" not in data:
        raise ValueError(f"Channels file missing 'channels' key: {filepath}")

    channels: list[Channel] = []

    for raw_channel in data["channels"]:
        channel_name = str(raw_channel["name"]).strip()
        protocol_block = raw_channel.get("protocol", {})
        protocol_type = str(protocol_block.get("type", ""))
        bus_hw_id = int(protocol_block.get("bus_hw_id", 0))

        messages: list[ChannelMessage] = []
        for raw_msg in protocol_block.get("messages", []):
            try:
                msg = _parse_message(raw_msg)
                messages.append(msg)
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning(
                    "Skipping malformed message in channel '%s': %s",
                    channel_name, exc,
                )
                continue

        channel = Channel(
            name=channel_name,
            protocol_type=protocol_type,
            bus_hw_id=bus_hw_id,
            messages=messages,
        )
        channels.append(channel)

    logger.info("Parsed %d channel(s) from %s", len(channels), filepath)
    return channels


def build_pdu_direction_map(channels: list[Channel]) -> dict[int, Direction]:
    """Build a mapping from **actual PDU ID** to :class:`Direction`.

    The channels file references PDUs with extended IDs (e.g. ``0x1401``)
    whereas the PDU definition files use the base ID (e.g. ``0x401``).  The
    common convention observed in FLYNC models is that the channel reference
    encodes a prefix (typically ``0x1000``) added to the real PDU ID:

        channel ref ``0x1401`` --> PDU id ``0x401``

    This function stores the direction under *both* the raw channel reference
    ID and the stripped (lower 12-bit masked) variant so that downstream
    consumers can look up either form.

    Parameters
    ----------
    channels:
        Parsed list of channels (output of :func:`parse_channels`).

    Returns
    -------
    dict[int, Direction]
        PDU ID (in various representations) to direction mapping.
    """
    direction_map: dict[int, Direction] = {}

    for channel in channels:
        for msg in channel.messages:
            if msg.pdu_id is None:
                continue

            direction = _determine_direction(msg.sender, msg.receivers)
            if direction == Direction.UNKNOWN:
                continue

            pdu_ref = msg.pdu_id

            # Store the raw reference ID.
            _record_direction(direction_map, pdu_ref, direction, msg.name)

            # Attempt to strip common prefixes to recover the base PDU ID.
            # For example: 0x1401 & 0x0FFF = 0x0401, but also try masking
            # off the top nibble(s) by subtracting common bases.
            # Strategy: strip the highest hex digit(s) that form a 0x1000-aligned
            # prefix.  We try multiple mask widths so that both short IDs
            # (0x1401 -> 0x401) and long IDs work.
            for mask in (0x0FFF, 0x00FFFFFF, 0x0000FFFF):
                stripped = pdu_ref & mask
                if stripped != pdu_ref and stripped != 0:
                    _record_direction(direction_map, stripped, direction, msg.name)

    logger.info(
        "Built PDU direction map with %d entries from %d channel(s)",
        len(direction_map), len(channels),
    )
    return direction_map


def _record_direction(
    direction_map: dict[int, Direction],
    pdu_id: int,
    direction: Direction,
    msg_name: str,
) -> None:
    """Insert *direction* for *pdu_id*, warning on conflicts."""
    existing = direction_map.get(pdu_id)
    if existing is not None and existing != direction:
        logger.warning(
            "Conflicting directions for PDU 0x%X (message '%s'): "
            "existing=%s, new=%s -- keeping first",
            pdu_id, msg_name, existing.value, direction.value,
        )
        return
    direction_map[pdu_id] = direction
