"""Parser for FLYNC PDU YAML files.

Reads PDU definition files and constructs Signal and PDU model objects.
Signals within a PDU are laid out sequentially in bit order -- start_bit
is computed by accumulating bit_length values from the first signal onwards.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from ..models.signal import PDU, Signal, ValueTableEntry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_hex_id(raw_value: Any) -> int:
    """Parse an ID field that may be a hex string (e.g. '0x401') or an int."""
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, str):
        raw_value = raw_value.strip()
        try:
            return int(raw_value, 16) if raw_value.startswith("0x") or raw_value.startswith("0X") else int(raw_value)
        except ValueError:
            raise ValueError(f"Cannot parse ID value: {raw_value!r}")
    raise TypeError(f"Unexpected type for ID field: {type(raw_value).__name__} ({raw_value!r})")


def _parse_value_table(raw_entries: list[dict[str, Any]] | None) -> list[ValueTableEntry]:
    """Parse the optional value_table list from a signal definition."""
    if not raw_entries:
        return []
    entries: list[ValueTableEntry] = []
    for entry in raw_entries:
        entries.append(
            ValueTableEntry(
                num_value=int(entry["num_value"]),
                description=str(entry["description"]),
            )
        )
    return entries


def _parse_compu_methods(raw: Any) -> list[str]:
    """Normalise the optional compu_methods field to a list of strings.

    In the YAML files this field can appear as a single string value or as a
    list of strings.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return [str(raw)]


def _parse_signal(raw_signal: dict[str, Any], current_bit_offset: int) -> tuple[Signal, int]:
    """Parse a single signal dict and return (Signal, next_bit_offset).

    The *current_bit_offset* is the start bit for this signal.  The function
    returns the updated offset (current + bit_length) so the caller can feed
    it to the next signal.
    """
    # Signal names in the YAML occasionally have leading/trailing whitespace.
    name = str(raw_signal["name"]).strip()
    description = str(raw_signal.get("description", ""))
    bit_length = int(raw_signal["bit_length"])
    base_data_type = str(raw_signal["base_data_type"])
    endianness = str(raw_signal["endianness"])

    scale = float(raw_signal.get("scale", 1.0))
    offset = float(raw_signal.get("offset", 0.0))
    lower_limit = float(raw_signal.get("lower_limit", 0))
    upper_limit = float(raw_signal.get("upper_limit", 0))

    compu_methods = _parse_compu_methods(raw_signal.get("compu_methods"))
    value_table = _parse_value_table(raw_signal.get("value_table"))

    signal = Signal(
        name=name,
        description=description,
        bit_length=bit_length,
        base_data_type=base_data_type,
        endianness=endianness,
        lower_limit=lower_limit,
        upper_limit=upper_limit,
        scale=scale,
        offset=offset,
        compu_methods=compu_methods,
        value_table=value_table,
        start_bit=current_bit_offset,
        # bitmask is computed automatically by Signal.__post_init__
    )

    next_offset = current_bit_offset + bit_length
    return signal, next_offset


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_pdu_file(filepath: Path) -> PDU:
    """Parse a single PDU YAML file and return a :class:`PDU` instance.

    Parameters
    ----------
    filepath:
        Path to a ``*.flync.yaml`` PDU definition file.

    Returns
    -------
    PDU
        The parsed PDU with all signals populated and start_bit computed.

    Raises
    ------
    FileNotFoundError
        If *filepath* does not exist.
    yaml.YAMLError
        If the file cannot be parsed as valid YAML.
    KeyError
        If required fields are missing from the YAML structure.
    """
    filepath = Path(filepath)
    if not filepath.is_file():
        raise FileNotFoundError(f"PDU file not found: {filepath}")

    logger.debug("Parsing PDU file: %s", filepath)

    with open(filepath, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if data is None:
        raise ValueError(f"PDU file is empty or contains no YAML data: {filepath}")

    pdu_name = str(data["name"]).strip()
    pdu_id = _parse_hex_id(data["id"])
    pdu_length = int(data["length"])
    pdu_type = str(data.get("type", "standard"))

    # Parse signals with sequential start_bit accumulation.
    signals: list[Signal] = []
    current_bit_offset = 0

    raw_signals = data.get("signals", [])
    if raw_signals is None:
        raw_signals = []

    for idx, raw_entry in enumerate(raw_signals):
        # Each entry is wrapped in a "signal" key: {signal: {name: ..., ...}}
        if isinstance(raw_entry, dict) and "signal" in raw_entry:
            raw_signal = raw_entry["signal"]
        else:
            # Tolerate unwrapped signal dicts as well.
            raw_signal = raw_entry

        try:
            signal, current_bit_offset = _parse_signal(raw_signal, current_bit_offset)
            signals.append(signal)
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning(
                "Skipping signal at index %d in PDU '%s' (%s): %s",
                idx, pdu_name, filepath, exc,
            )
            continue

    pdu = PDU(
        name=pdu_name,
        pdu_id=pdu_id,
        length=pdu_length,
        pdu_type=pdu_type,
        signals=signals,
    )

    logger.info(
        "Parsed PDU '%s' (id=0x%X, %d signals) from %s",
        pdu.name, pdu.pdu_id, len(pdu.signals), filepath.name,
    )
    return pdu


def parse_pdu_directory(dirpath: Path) -> dict[str, PDU]:
    """Parse all PDU YAML files in a directory.

    Recursively finds files matching ``*.flync.yaml`` and parses each one.

    Parameters
    ----------
    dirpath:
        Path to the directory containing PDU definition files.

    Returns
    -------
    dict[str, PDU]
        A mapping from PDU name to the parsed :class:`PDU` object.
    """
    dirpath = Path(dirpath)
    if not dirpath.is_dir():
        raise NotADirectoryError(f"PDU directory not found: {dirpath}")

    pdus: dict[str, PDU] = {}
    yaml_files = sorted(dirpath.glob("*.flync.yaml"))

    if not yaml_files:
        logger.warning("No *.flync.yaml files found in %s", dirpath)
        return pdus

    for yaml_file in yaml_files:
        try:
            pdu = parse_pdu_file(yaml_file)
            if pdu.name in pdus:
                logger.warning(
                    "Duplicate PDU name '%s' -- overwriting previous entry "
                    "(previous id=0x%X, new id=0x%X)",
                    pdu.name, pdus[pdu.name].pdu_id, pdu.pdu_id,
                )
            pdus[pdu.name] = pdu
        except Exception as exc:
            logger.error("Failed to parse PDU file %s: %s", yaml_file, exc)
            continue

    logger.info("Parsed %d PDU(s) from %s", len(pdus), dirpath)
    return pdus
