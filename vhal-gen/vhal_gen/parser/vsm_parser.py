"""Parser for FLYNC VSM (Vehicle State Manager) global state definitions.

Reads ``vsm_states.flync.yaml`` and returns a list of :class:`GlobalState`
objects that describe the vehicle's operating modes and their ECU
participants.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from ..models.signal import GlobalState

logger = logging.getLogger(__name__)


def parse_vsm_states(filepath: Path) -> list[GlobalState]:
    """Parse a VSM states YAML file.

    Parameters
    ----------
    filepath:
        Path to the ``vsm_states.flync.yaml`` file.

    Returns
    -------
    list[GlobalState]
        All global states defined in the file.

    Raises
    ------
    FileNotFoundError
        If *filepath* does not exist.
    yaml.YAMLError
        If the file contains invalid YAML.
    """
    filepath = Path(filepath)
    if not filepath.is_file():
        raise FileNotFoundError(f"VSM states file not found: {filepath}")

    logger.debug("Parsing VSM states file: %s", filepath)

    with open(filepath, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if data is None or "global_states" not in data:
        raise ValueError(f"VSM states file missing 'global_states' key: {filepath}")

    states: list[GlobalState] = []

    for raw_state in data["global_states"]:
        try:
            name = str(raw_state["name"]).strip()
            state_id = int(raw_state["id"])
            participants = [str(p).strip() for p in raw_state.get("participants", [])]
            is_default = bool(raw_state.get("is_default", False))

            state = GlobalState(
                name=name,
                state_id=state_id,
                participants=participants,
                is_default=is_default,
            )
            states.append(state)
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Skipping malformed global state entry: %s", exc)
            continue

    logger.info("Parsed %d global state(s) from %s", len(states), filepath)
    return states
