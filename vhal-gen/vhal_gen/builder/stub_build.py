"""Stub-based compile checker for generated VHAL bridge code.

Runs ``clang++ -fsyntax-only`` against the generated .cpp files using
minimal stub headers for AIDL types, Android logging, and jsoncpp.
This validates that the generated C++ is syntactically correct without
requiring a full AOSP build environment.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Iterator


class StubBuilder:
    """Compile-check generated bridge code using stub headers."""

    STUBS_DIR = Path(__file__).parent.parent / "stubs"

    # Source files to check (relative to bridge_dir).
    SOURCES = ["BridgeVehicleHardware.cpp", "FlyncDaemon.cpp"]

    def _find_clang(self) -> str | None:
        """Return the path to clang++, or None if not found."""
        return shutil.which("clang++")

    def _build_includes(self, vhal_root: Path) -> list[str]:
        """Return -I flags for clang++."""
        bridge_dir = vhal_root / "impl" / "bridge"
        dirs = [
            self.STUBS_DIR,                         # stubs first (shadows VehicleHalTypes.h)
            bridge_dir,                             # bridge headers (IpcProtocol.h, etc.)
            bridge_dir / "sdk" / "app" / "swc",     # Read_App_Signal_Data.h, Write_...
            bridge_dir / "sdk" / "com" / "include",  # COM stack headers
            bridge_dir / "sdk" / "can_io" / "include",
            vhal_root / "impl" / "hardware" / "include",  # IVehicleHardware.h (real)
        ]
        flags: list[str] = []
        for d in dirs:
            flags.extend(["-I", str(d)])
        return flags

    def compile_check(self, vhal_root: Path) -> Iterator[str]:
        """Run clang++ -fsyntax-only on each bridge .cpp file.

        Args:
            vhal_root: Root of the pulled VHAL source tree
                       (e.g. ``output/Vhal-test1``).

        Yields:
            Status/diagnostic lines suitable for streaming to UI or CLI.
        """
        clang = self._find_clang()
        if not clang:
            yield "ERROR: clang++ not found in PATH"
            return

        bridge_dir = vhal_root / "impl" / "bridge"
        if not bridge_dir.is_dir():
            yield f"ERROR: bridge directory not found: {bridge_dir}"
            return

        includes = self._build_includes(vhal_root)
        passed = 0
        failed = 0

        for src_name in self.SOURCES:
            src_path = bridge_dir / src_name
            if not src_path.exists():
                yield f"SKIP {src_name} — file not found"
                continue

            cmd = [
                clang,
                "-std=c++17",
                "-fsyntax-only",
                "-Wno-unused-value",
                *includes,
                str(src_path),
            ]
            yield f"Checking {src_name} ..."

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except subprocess.TimeoutExpired:
                yield f"FAIL {src_name} — clang++ timed out"
                failed += 1
                continue

            if result.returncode == 0:
                yield f"PASS {src_name}"
                passed += 1
            else:
                yield f"FAIL {src_name}"
                # Show diagnostics (stderr contains clang error messages).
                for line in result.stderr.strip().splitlines():
                    yield f"  {line}"
                failed += 1

        yield ""
        if failed == 0:
            yield f"All {passed} file(s) passed compile check."
        else:
            yield f"{failed} file(s) failed, {passed} passed."
