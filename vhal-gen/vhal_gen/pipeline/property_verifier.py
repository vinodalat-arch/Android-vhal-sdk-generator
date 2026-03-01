"""Verify vehicle properties are accessible on the emulator via car_service."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator

from ..classifier.standard_properties import STANDARD_PROPERTIES
from ..shell.runner import ShellRunner


# Regex to match "VehicleProperty::SOME_NAME"
_VHPROP_RE = re.compile(r"^VehicleProperty::(\w+)$")


class PropertyVerifier:
    """Reads DefaultProperties.json and verifies each property on the device."""

    def __init__(self, shell: ShellRunner | None = None) -> None:
        self._shell = shell or ShellRunner()

    @staticmethod
    def _resolve_property_id(raw_id) -> tuple[str, str]:
        """Resolve a property ID from DefaultProperties.json to (hex_str, display_label).

        Handles three formats:
        - int:  556924416  → ("0x21200100", "0x21200100")
        - hex string: "0x21200100" → ("0x21200100", "0x21200100")
        - AOSP name: "VehicleProperty::HEADLIGHTS_STATE" → ("0xE010A00", "HEADLIGHTS_STATE")
        """
        if isinstance(raw_id, int):
            hex_str = f"0x{raw_id:X}"
            return hex_str, hex_str

        s = str(raw_id)
        m = _VHPROP_RE.match(s)
        if m:
            name = m.group(1)
            numeric = STANDARD_PROPERTIES.get(name)
            if numeric is not None:
                hex_str = f"0x{numeric:X}"
                return hex_str, name
            # Unknown standard property — pass the name through
            return s, name

        # Already a hex string like "0x21200101"
        return s, s

    def verify(
        self,
        properties_json_path: Path,
    ) -> Iterator[str]:
        """Verify all properties in DefaultProperties.json are accessible.

        Args:
            properties_json_path: Path to DefaultProperties.json (local copy).

        Yields:
            Status lines.
        """
        if not properties_json_path.is_file():
            yield f"ERROR: DefaultProperties.json not found at {properties_json_path}"
            return

        try:
            raw = json.loads(properties_json_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            yield f"ERROR: Failed to parse DefaultProperties.json — {exc}"
            return

        # The file uses AOSP apiVersion wrapper format
        properties = raw.get("properties", raw) if isinstance(raw, dict) else raw
        if not isinstance(properties, list):
            yield "ERROR: Unexpected DefaultProperties.json format"
            return

        yield f"Verifying {len(properties)} properties on device..."

        passed = 0
        failed = 0

        for prop_entry in properties:
            raw_id = prop_entry.get("property")
            if raw_id is None:
                continue

            prop_id_hex, label = self._resolve_property_id(raw_id)

            # Query via car_service (trunk builds use "get-property-value")
            rc, stdout, stderr = self._shell.run(
                [
                    "adb", "shell", "cmd", "car_service",
                    "get-property-value", prop_id_hex,
                ],
                timeout=10,
            )

            if rc == 0 and "error" not in stdout.lower():
                yield f"PASS {label} ({prop_id_hex})"
                passed += 1
            else:
                detail = stdout.strip() or stderr.strip()
                yield f"FAIL {label} ({prop_id_hex}) — {detail[:120]}"
                failed += 1

        yield ""
        if failed == 0:
            yield f"All {passed} properties verified on device."
        else:
            yield f"{failed} properties failed, {passed} passed."
