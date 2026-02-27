"""Orchestrator that loads a complete FLYNC model from a directory tree.

Expected directory layout::

    <model_dir>/
        general/
            channels/
                channels.yaml
                pdus/
                    *.flync.yaml      # PDU definition files
            vsm_states.flync.yaml     # optional
        system_metadata.flync.yaml    # optional

The loader ties together the PDU, channel, and VSM parsers to produce a
single :class:`FlyncModel` instance with all cross-references resolved
(e.g. PDU directions derived from channel sender/receiver information).
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from ..models.signal import Direction, FlyncModel
from .channel_parser import build_pdu_direction_map, parse_channels
from .pdu_parser import parse_pdu_directory
from .vsm_parser import parse_vsm_states

logger = logging.getLogger(__name__)


def _load_metadata(model_dir: Path) -> dict:
    """Attempt to load optional system metadata from the model directory."""
    metadata_path = model_dir / "system_metadata.flync.yaml"
    if not metadata_path.is_file():
        logger.debug("No system_metadata.flync.yaml found in %s", model_dir)
        return {}

    try:
        with open(metadata_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Failed to load system metadata from %s: %s", metadata_path, exc)
        return {}


def load_flync_model(model_dir: Path) -> FlyncModel:
    """Load a complete FLYNC model from *model_dir*.

    Steps
    -----
    1. Discover and parse all PDU files under ``general/channels/pdus/``.
    2. Parse ``general/channels/channels.yaml``.
    3. Build a PDU-ID-to-direction map from channel definitions.
    4. Apply the resolved directions to every parsed PDU.
    5. Parse ``general/vsm_states.flync.yaml`` (if present).
    6. Optionally load system-level metadata.
    7. Return the assembled :class:`FlyncModel`.

    Parameters
    ----------
    model_dir:
        Root directory of the FLYNC model (the folder that contains the
        ``general/`` sub-directory).

    Returns
    -------
    FlyncModel
        The fully assembled model.

    Raises
    ------
    FileNotFoundError
        If the required PDU directory or channels file does not exist.
    """
    model_dir = Path(model_dir)
    if not model_dir.is_dir():
        raise NotADirectoryError(f"Model directory not found: {model_dir}")

    logger.info("Loading FLYNC model from %s", model_dir)

    # Auto-detect nested model directory (e.g., flync-model-dev-2/flync-model-dev/)
    pdu_dir = model_dir / "general" / "channels" / "pdus"
    if not pdu_dir.is_dir():
        # Search one level deep for a subdirectory with general/channels/pdus
        for child in model_dir.iterdir():
            if child.is_dir():
                candidate = child / "general" / "channels" / "pdus"
                if candidate.is_dir():
                    logger.info("Found nested model directory: %s", child)
                    model_dir = child
                    pdu_dir = candidate
                    break

    # ----- 1. Parse PDU files ------------------------------------------------
    if not pdu_dir.is_dir():
        raise FileNotFoundError(
            f"PDU directory not found: {pdu_dir}. "
            "Expected layout: <model_dir>/general/channels/pdus/"
        )

    pdus = parse_pdu_directory(pdu_dir)
    logger.info("Loaded %d PDU(s)", len(pdus))

    # ----- 2. Parse channels -------------------------------------------------
    channels_file = model_dir / "general" / "channels" / "channels.yaml"
    if not channels_file.is_file():
        raise FileNotFoundError(
            f"Channels file not found: {channels_file}. "
            "Expected layout: <model_dir>/general/channels/channels.yaml"
        )

    channels = parse_channels(channels_file)
    logger.info("Loaded %d channel(s)", len(channels))

    # ----- 3. Build direction map --------------------------------------------
    direction_map = build_pdu_direction_map(channels)

    # ----- 4. Apply directions to PDUs ---------------------------------------
    resolved_count = 0
    for pdu in pdus.values():
        direction = direction_map.get(pdu.pdu_id, Direction.UNKNOWN)
        if direction != Direction.UNKNOWN:
            pdu.direction = direction
            resolved_count += 1
            logger.debug(
                "PDU '%s' (0x%X) direction resolved to %s",
                pdu.name, pdu.pdu_id, direction.value,
            )
        else:
            logger.debug(
                "PDU '%s' (0x%X) direction remains UNKNOWN",
                pdu.name, pdu.pdu_id,
            )

    logger.info(
        "Resolved direction for %d / %d PDU(s)",
        resolved_count, len(pdus),
    )

    # ----- 5. Parse VSM states (optional) ------------------------------------
    global_states = []
    vsm_path = model_dir / "general" / "vsm_states.flync.yaml"
    if vsm_path.is_file():
        try:
            global_states = parse_vsm_states(vsm_path)
            logger.info("Loaded %d global state(s)", len(global_states))
        except Exception as exc:
            logger.warning("Failed to parse VSM states: %s", exc)
    else:
        logger.debug("No vsm_states.flync.yaml found; skipping VSM states")

    # ----- 6. Load metadata --------------------------------------------------
    metadata = _load_metadata(model_dir)

    # ----- 7. Assemble model -------------------------------------------------
    model = FlyncModel(
        pdus=pdus,
        channels=channels,
        global_states=global_states,
        metadata=metadata,
    )

    logger.info(
        "FLYNC model loaded: %d PDU(s), %d channel(s), %d global state(s)",
        len(model.pdus), len(model.channels), len(model.global_states),
    )
    return model
