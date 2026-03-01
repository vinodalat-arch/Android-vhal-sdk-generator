"""Stub-based compile checker for generated VHAL bridge code.

Runs ``clang++ -fsyntax-only`` against **all** .cpp/.cc files under the
bridge directory — generated bridge code, the VehicleDaemon, and the full
Vehicle Body SDK reference code (com, can_io, app/swc).

**Mandatory requirement**: The compile check MUST cover the entire daemon
codebase — both the generated bridge files (BridgeVehicleHardware.cpp,
VehicleDaemon.cpp) AND all SDK reference source files (ComConfig, CanConfig,
com_utils, iodata, Read/Write_App_Signal_Data).  When SDK files are not
copied into ``bridge/sdk/`` (i.e. ``generate`` was run without ``--sdk-dir``),
they are discovered from the original SDK source directory passed via
``sdk_dir``.

Minimal stub headers for AIDL types, Android logging, and jsoncpp are
placed first on the include path so they shadow the real AOSP headers
that are missing outside a full build environment.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path
from typing import Iterator

# SDK source files that must be compiled alongside the generated bridge code.
# Keys are paths relative to the SDK source root (e.g. performance-stack-.../src/).
# These match the SDK_FILE_MAP in generator_engine.py.
_SDK_SOURCE_RELPATHS: list[str] = [
    "com/src/ComConfig.cpp",
    "com/src/CanConfig.cpp",
    "com/src/com_utils.cpp",
    "can_io/src/iodata.cc",
    "app/swc/Read_App_Signal_Data.cpp",
    "app/swc/Write_App_Signal_Data.cpp",
]


class StubBuilder:
    """Compile-check all bridge code (generated + SDK) using stub headers."""

    STUBS_DIR = Path(__file__).parent.parent / "stubs"

    def _find_clang(self) -> str | None:
        """Return the path to clang++, or None if not found."""
        return shutil.which("clang++")

    def _discover_sources(
        self, bridge_dir: Path, sdk_dir: Path | None = None
    ) -> list[Path]:
        """Find all .cpp and .cc files to compile-check.

        Sources include:
        1. All .cpp/.cc under bridge_dir (generated code + SDK if copied there)
        2. SDK reference source files from sdk_dir (when bridge/sdk/ doesn't
           exist, i.e. generate was run without --sdk-dir)

        This ensures the ENTIRE daemon codebase is covered — both generated
        bridge files and SDK reference code.
        """
        sources: list[Path] = []

        # 1. All source files under bridge/
        for ext in ("*.cpp", "*.cc"):
            sources.extend(bridge_dir.rglob(ext))
        # Exclude test-apk directory (Java/Android test code, not compilable)
        # Exclude mw-fdnrouter main.cc (standalone router binary, not part of daemon)
        sources = [
            s for s in sources
            if "test-apk" not in s.parts
            and not (s.name == "main.cc" and "mw-fdnrouter" in s.parts)
        ]

        # 2. If SDK wasn't copied into bridge/sdk/, pull sources from sdk_dir
        sdk_in_bridge = bridge_dir / "sdk"
        if not sdk_in_bridge.is_dir() and sdk_dir and sdk_dir.is_dir():
            for rel in _SDK_SOURCE_RELPATHS:
                src = sdk_dir / rel
                if src.is_file():
                    sources.append(src)

        return sorted(set(sources))

    def _build_flags(
        self, vhal_root: Path, sdk_dir: Path | None = None
    ) -> list[str]:
        """Return -I and -D flags for clang++."""
        bridge_dir = vhal_root / "impl" / "bridge"
        dirs: list[Path] = [
            self.STUBS_DIR,                             # stubs first (shadows VehicleHalTypes.h)
            bridge_dir,                                 # bridge headers (IpcProtocol.h, etc.)
        ]

        # SDK headers — prefer the copied tree under bridge/sdk/, but fall
        # back to the original SDK source directory if sdk/ wasn't copied
        # (i.e. generate was run without --sdk-dir).
        sdk_in_bridge = bridge_dir / "sdk"
        if sdk_in_bridge.is_dir():
            dirs.extend([
                # Signal layer
                sdk_in_bridge / "app" / "swc",
                sdk_in_bridge / "com" / "include",
                sdk_in_bridge / "com" / "src",
                sdk_in_bridge / "can_io" / "include",
                sdk_in_bridge / "can_io" / "src",
                # Transport layer
                sdk_in_bridge / "mw-fdnrouter" / "include",
                sdk_in_bridge / "m2s" / "include",
                sdk_in_bridge / "m2s" / "include" / "common" / "include",
                sdk_in_bridge / "s2m" / "include",
                # IPC headers (iceoryx / iceoryx2)
                sdk_in_bridge / "publish_subscribe" / "include" / "iceoryx" / "v2.95.7",
                sdk_in_bridge / "publish_subscribe" / "include" / "iceoryx2" / "v0.6.1",
            ])
        elif sdk_dir and sdk_dir.is_dir():
            # Original SDK source layout: sdk_dir/{app/swc, com/include, ...}
            dirs.extend([
                # Signal layer
                sdk_dir / "app" / "swc",
                sdk_dir / "com" / "include",
                sdk_dir / "com" / "src",
                sdk_dir / "can_io" / "include",
                sdk_dir / "can_io" / "src",
                # Transport layer
                sdk_dir / "mw-fdnrouter" / "include",
                sdk_dir / "m2s" / "include",
                sdk_dir / "m2s" / "include" / "common" / "include",
                sdk_dir / "s2m" / "include",
                # IPC headers (iceoryx / iceoryx2)
                sdk_dir / "publish_subscribe" / "rootfs" / "include" / "iceoryx" / "v2.95.7",
                sdk_dir / "publish_subscribe" / "rootfs" / "include" / "iceoryx2" / "v0.6.1",
            ])

        dirs.append(
            vhal_root / "impl" / "hardware" / "include",  # IVehicleHardware.h
        )

        flags: list[str] = []
        for d in dirs:
            flags.extend(["-I", str(d)])

        # On macOS, be32toh/htobe32 live in <libkern/OSByteOrder.h> with
        # different names.  The SDK reference code (iodata.cc) expects the
        # Linux <endian.h> API, so we provide compatibility macros.
        if platform.system() == "Darwin":
            flags.extend([
                "-include", "libkern/OSByteOrder.h",
                "-Dbe32toh=OSSwapBigToHostInt32",
                "-Dhtobe32=OSSwapHostToBigInt32",
            ])

        return flags

    def compile_check(
        self, vhal_root: Path, sdk_dir: Path | None = None
    ) -> Iterator[str]:
        """Run clang++ -fsyntax-only on each .cpp/.cc file under bridge/.

        Checks all source files: generated bridge code (BridgeVehicleHardware,
        VehicleDaemon) and the full Vehicle Body SDK reference code (com_utils,
        ComConfig, CanConfig, iodata, Read/Write_App_Signal_Data).

        Args:
            vhal_root: Root of the pulled VHAL source tree
                       (e.g. ``output/Vhal-test1``).
            sdk_dir: Optional path to the original Vehicle Body SDK source
                     directory.  Used as a fallback when SDK files haven't
                     been copied into bridge/sdk/.

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

        # Check if SDK headers are available
        sdk_in_bridge = bridge_dir / "sdk"
        has_sdk = sdk_in_bridge.is_dir() or (sdk_dir and sdk_dir.is_dir())
        if not has_sdk:
            yield ("WARNING: SDK files not found in bridge/sdk/ and no "
                   "--sdk-dir provided. VehicleDaemon.cpp will likely fail "
                   "(missing Read_App_Signal_Data.h).")

        sources = self._discover_sources(bridge_dir, sdk_dir=sdk_dir)
        if not sources:
            yield "ERROR: no .cpp/.cc source files found under bridge/"
            return

        yield f"Found {len(sources)} source file(s) under bridge/"
        flags = self._build_flags(vhal_root, sdk_dir=sdk_dir)
        passed = 0
        failed = 0

        for src_path in sources:
            # Show path relative to bridge_dir for bridge files, or
            # sdk/<relative> for SDK files from the original source tree.
            try:
                rel_name = str(src_path.relative_to(bridge_dir))
            except ValueError:
                # File is outside bridge_dir (SDK source from sdk_dir)
                if sdk_dir:
                    try:
                        rel_name = "sdk/" + str(src_path.relative_to(sdk_dir))
                    except ValueError:
                        rel_name = src_path.name
                else:
                    rel_name = src_path.name

            cmd = [
                clang,
                "-std=c++17",
                "-fsyntax-only",
                "-Wno-unused-value",
                *flags,
                str(src_path),
            ]
            yield f"Checking {rel_name} ..."

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except subprocess.TimeoutExpired:
                yield f"FAIL {rel_name} — clang++ timed out"
                failed += 1
                continue

            if result.returncode == 0:
                yield f"PASS {rel_name}"
                passed += 1
            else:
                yield f"FAIL {rel_name}"
                # Show diagnostics (stderr contains clang error messages).
                for line in result.stderr.strip().splitlines():
                    yield f"  {line}"
                failed += 1

        yield ""
        if failed == 0:
            yield f"All {passed} file(s) passed compile check."
        else:
            yield f"{failed} file(s) failed, {passed} passed."
