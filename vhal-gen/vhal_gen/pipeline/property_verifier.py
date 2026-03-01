"""Verify vehicle properties are accessible on the emulator via car_service."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from ..shell.runner import ShellRunner


class PropertyVerifier:
    """Reads DefaultProperties.json and verifies each property on the device."""

    def __init__(self, shell: ShellRunner | None = None) -> None:
        self._shell = shell or ShellRunner()

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
            prop_id = prop_entry.get("property")
            if prop_id is None:
                continue

            # property is stored as a decimal integer in the JSON
            prop_id_hex = f"0x{prop_id:X}" if isinstance(prop_id, int) else str(prop_id)

            # Query via car_service (trunk builds use "get-property-value")
            rc, stdout, stderr = self._shell.run(
                [
                    "adb", "shell", "cmd", "car_service",
                    "get-property-value", prop_id_hex,
                ],
                timeout=10,
            )

            if rc == 0 and "error" not in stdout.lower():
                yield f"PASS {prop_id_hex}"
                passed += 1
            else:
                detail = stdout.strip() or stderr.strip()
                yield f"FAIL {prop_id_hex} — {detail[:120]}"
                failed += 1

        yield ""
        if failed == 0:
            yield f"All {passed} properties verified on device."
        else:
            yield f"{failed} properties failed, {passed} passed."
