"""Orchestrator for code generation from classified signal mappings."""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader

from ..models.signal import FlyncModel, PDU
from ..models.vehicle_property import PropertyMapping

logger = logging.getLogger(__name__)

# Template directory relative to this file
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

# SDK files to copy verbatim from the Vehicle Body SDK source tree.
# Keys are source-relative paths, values are destination-relative paths
# under bridge/sdk/.
SDK_FILE_MAP: dict[str, str] = {
    "com/include/ComConfig.h": "sdk/com/include/ComConfig.h",
    "com/include/CanConfig.h": "sdk/com/include/CanConfig.h",
    "com/include/com_utils.h": "sdk/com/include/com_utils.h",
    "com/src/ComConfig.cpp": "sdk/com/src/ComConfig.cpp",
    "com/src/CanConfig.cpp": "sdk/com/src/CanConfig.cpp",
    "com/src/com_utils.cpp": "sdk/com/src/com_utils.cpp",
    "can_io/include/iodata.h": "sdk/can_io/include/iodata.h",
    "can_io/src/iodata.cc": "sdk/can_io/src/iodata.cc",
    "app/swc/Read_App_Signal_Data.h": "sdk/app/swc/Read_App_Signal_Data.h",
    "app/swc/Read_App_Signal_Data.cpp": "sdk/app/swc/Read_App_Signal_Data.cpp",
    "app/swc/Write_App_Signal_Data.h": "sdk/app/swc/Write_App_Signal_Data.h",
    "app/swc/Write_App_Signal_Data.cpp": "sdk/app/swc/Write_App_Signal_Data.cpp",
}

# SDK directories to copy recursively (transport layer + iceoryx2 headers).
# Keys are source-relative directory paths, values are destination-relative
# paths under bridge/.
SDK_DIR_MAP: dict[str, str] = {
    # mw-fdnrouter: UDP transport, routing, configuration
    "mw-fdnrouter/include": "sdk/mw-fdnrouter/include",
    "mw-fdnrouter/src": "sdk/mw-fdnrouter/src",
    # m2s: message-to-signal layer
    "m2s/include": "sdk/m2s/include",
    "m2s/src": "sdk/m2s/src",
    # s2m: signal-to-message layer
    "s2m/include": "sdk/s2m/include",
    "s2m/src": "sdk/s2m/src",
    # iceoryx / iceoryx2 headers (IPC pub/sub used by transport layer)
    "publish_subscribe/rootfs/include/iceoryx": "sdk/publish_subscribe/include/iceoryx",
    "publish_subscribe/rootfs/include/iceoryx2": "sdk/publish_subscribe/include/iceoryx2",
}


class GeneratorEngine:
    """Generates all output files from FLYNC model and signal mappings."""

    def __init__(
        self,
        mappings: list[PropertyMapping],
        model: FlyncModel,
        sdk_source_dir: Path | None = None,
    ):
        self.mappings = mappings
        self.model = model
        self.sdk_source_dir = sdk_source_dir
        self._env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate(self, vhal_root: Path) -> list[Path]:
        """Generate into the pulled VHAL tree.

        Writes generated files to impl/bridge/, modifies VehicleService.cpp
        and vhal/Android.bp in-place.

        Args:
            vhal_root: Path to automotive/vehicle/aidl (the sparse checkout root)

        Returns:
            List of generated/modified file paths.
        """
        bridge_dir = vhal_root / "impl" / "bridge"
        test_dir = bridge_dir / "test-apk"
        bridge_dir.mkdir(parents=True, exist_ok=True)
        test_dir.mkdir(parents=True, exist_ok=True)

        generated = []

        # Deduplicate mappings by (property_id, area_id) -- the same signal
        # name can appear in multiple PDUs but produces only one property.
        unique_mappings = self._deduplicate_mappings()

        vendor_mappings = [m for m in unique_mappings if m.is_vendor]
        standard_mappings = [m for m in unique_mappings if m.is_standard]

        # Build signal entries for daemon templates
        signal_entries = self._build_signal_entries()
        pdu_entries = self._build_pdu_entries()

        # Context shared across templates
        ctx = {
            "mappings": unique_mappings,
            "vendor_mappings": vendor_mappings,
            "standard_mappings": standard_mappings,
            "signal_entries": signal_entries,
            "pdu_entries": pdu_entries,
            "config_json_path": "/vendor/etc/automotive/vhal/DefaultProperties.json",
        }

        # Files to generate: (template_name, output_path)
        file_map = [
            ("DefaultProperties.json.j2", bridge_dir / "DefaultProperties.json"),
            ("VendorProperties.h.j2", bridge_dir / "VendorProperties.h"),
            ("IpcProtocol.h.j2", bridge_dir / "IpcProtocol.h"),
            ("BridgeVehicleHardware.h.j2", bridge_dir / "BridgeVehicleHardware.h"),
            ("BridgeVehicleHardware.cpp.j2", bridge_dir / "BridgeVehicleHardware.cpp"),
            ("VehicleDaemon.h.j2", bridge_dir / "VehicleDaemon.h"),
            ("VehicleDaemon.cpp.j2", bridge_dir / "VehicleDaemon.cpp"),
            ("Android.bp.j2", bridge_dir / "Android.bp"),
            ("INTEGRATION.md.j2", bridge_dir / "INTEGRATION.md"),
            ("VhalTestActivity.java.j2", test_dir / "VhalTestActivity.java"),
            ("AndroidManifest.xml.j2", test_dir / "AndroidManifest.xml"),
            ("privapp-permissions-vhaltest.xml.j2", bridge_dir / "privapp-permissions-vhaltest.xml"),
            ("iceoryx2_stubs.cpp.j2", bridge_dir / "iceoryx2_stubs.cpp"),
        ]

        for template_name, output_path in file_map:
            try:
                template = self._env.get_template(template_name)
                content = template.render(**ctx)
                output_path.write_text(content)
                generated.append(output_path)
                logger.info("Generated: %s", output_path)
            except Exception as e:
                logger.error("Failed to generate %s: %s", template_name, e)
                raise

        # Copy SDK files if source directory is provided
        if self.sdk_source_dir is not None:
            sdk_files = self._copy_sdk_files(bridge_dir)
            generated.extend(sdk_files)

        # Auto-modify stock VHAL files
        self._patch_vehicle_service_cpp(vhal_root)
        self._modify_vhal_android_bp(vhal_root)

        return generated

    def _patch_vehicle_service_cpp(self, vhal_root: Path) -> None:
        """Directly modify VehicleService.cpp to use BridgeVehicleHardware.

        Performs in-place string replacements — no patch file needed.
        """
        vs_path = vhal_root / "impl" / "vhal" / "src" / "VehicleService.cpp"
        if not vs_path.exists():
            logger.warning("VehicleService.cpp not found at %s — skipping", vs_path)
            return

        content = vs_path.read_text()
        original = content

        # Replace include
        content = content.replace(
            "#include <FakeVehicleHardware.h>",
            "#include <BridgeVehicleHardware.h>",
        )

        # Replace using declaration
        content = content.replace(
            "using ::android::hardware::automotive::vehicle::fake::FakeVehicleHardware;",
            "using ::android::hardware::automotive::vehicle::bridge::BridgeVehicleHardware;",
        )

        # Replace instantiation (handles any whitespace before the variable)
        content = content.replace(
            "FakeVehicleHardware",
            "BridgeVehicleHardware",
        )

        if content != original:
            vs_path.write_text(content)
            logger.info("Patched VehicleService.cpp: FakeVehicleHardware -> BridgeVehicleHardware")
        else:
            logger.warning("VehicleService.cpp already patched or no FakeVehicleHardware found")

    def _modify_vhal_android_bp(self, vhal_root: Path) -> None:
        """Modify the cc_binary block in impl/vhal/Android.bp.

        Only touches the cc_binary block (the VHAL service binary).
        Leaves cc_library, cc_fuzz, and other blocks unchanged.
        """
        bp_path = vhal_root / "impl" / "vhal" / "Android.bp"
        if not bp_path.exists():
            logger.warning("vhal/Android.bp not found at %s — skipping", bp_path)
            return

        content = bp_path.read_text()
        original = content

        # Find the cc_binary block by tracking brace depth
        block_start, block_end = self._find_top_level_block(content, "cc_binary")
        if block_start is None:
            logger.warning("cc_binary block not found in vhal/Android.bp")
            return

        before = content[:block_start]
        block = content[block_start:block_end]
        after = content[block_end:]

        # 1. Remove FakeVehicleHardwareDefaults from defaults
        block = re.sub(
            r'[ \t]*"FakeVehicleHardwareDefaults",\n',
            "",
            block,
        )

        # 2. Replace FakeVehicleHardware with BridgeVehicleHardware in static_libs
        block = block.replace(
            '"FakeVehicleHardware"',
            '"BridgeVehicleHardware"',
        )

        # 3. Add libjsoncpp to shared_libs if not already present
        if '"libjsoncpp"' not in block:
            block = re.sub(
                r'(shared_libs:\s*\[)',
                r'\1\n        "libjsoncpp",',
                block,
            )

        # 4. Move libbase from shared_libs to static_libs (carries fmt symbols,
        # avoids trunk/A14 libbase.so ABI mismatch at deploy time)
        if '"libbase"' not in block:
            # Add libbase to static_libs
            block = re.sub(
                r'(static_libs:\s*\[)',
                r'\1\n        "libbase",',
                block,
            )

        # 5. Add required for DefaultProperties.json and vehicle-daemon
        # First remove any existing required: line (from previous runs)
        block = re.sub(r'\s*required:\s*\[[^\]]*\],?\n?', '\n', block)
        block = re.sub(
            r'(shared_libs:\s*\[[^\]]*\],)',
            r'\1\n    required: ["vehicle-DefaultProperties.json", "vehicle-daemon", "VhalTestApp"],',
            block,
            flags=re.DOTALL,
        )

        content = before + block + after

        if content != original:
            bp_path.write_text(content)
            logger.info("Modified vhal/Android.bp: swapped Fake->Bridge deps in cc_binary")
        else:
            logger.warning("vhal/Android.bp already modified or unexpected format")

    @staticmethod
    def _find_top_level_block(content: str, block_type: str) -> tuple:
        """Find the start and end of a top-level block (e.g. cc_binary {...}).

        Returns (start_index, end_index) or (None, None) if not found.
        """
        pattern = re.compile(rf'^{re.escape(block_type)}\s*\{{', re.MULTILINE)
        match = pattern.search(content)
        if not match:
            return None, None

        start = match.start()
        depth = 0
        i = match.end() - 1  # position of the opening brace
        while i < len(content):
            if content[i] == '{':
                depth += 1
            elif content[i] == '}':
                depth -= 1
                if depth == 0:
                    return start, i + 1
            i += 1

        return None, None

    def _copy_sdk_files(self, bridge_dir: Path) -> list[Path]:
        """Copy Vehicle Body SDK files into the bridge directory.

        Copies individual files from SDK_FILE_MAP and entire directories
        from SDK_DIR_MAP (transport layer, iceoryx2 headers).

        After copying, applies AOSP build compatibility patches (e.g.
        initializing variables to avoid -Werror,-Wsometimes-uninitialized).

        Returns list of copied file paths.
        """
        copied = []

        # 1. Copy individual files
        for src_rel, dst_rel in SDK_FILE_MAP.items():
            src_path = self.sdk_source_dir / src_rel
            dst_path = bridge_dir / dst_rel
            dst_path.parent.mkdir(parents=True, exist_ok=True)

            if not src_path.exists():
                logger.warning("SDK file not found: %s", src_path)
                continue

            shutil.copy2(src_path, dst_path)
            copied.append(dst_path)
            logger.info("Copied SDK: %s -> %s", src_path, dst_path)

        # 2. Copy directories recursively (transport layer + iceoryx2)
        for src_rel, dst_rel in SDK_DIR_MAP.items():
            src_dir = self.sdk_source_dir / src_rel
            dst_dir = bridge_dir / dst_rel

            if not src_dir.exists():
                logger.warning("SDK directory not found: %s", src_dir)
                continue

            if dst_dir.exists():
                shutil.rmtree(dst_dir)
            shutil.copytree(src_dir, dst_dir)

            dir_files = [f for f in dst_dir.rglob("*") if f.is_file()]
            copied.extend(dir_files)
            logger.info(
                "Copied SDK dir: %s -> %s (%d files)",
                src_dir, dst_dir, len(dir_files),
            )

        # Apply AOSP build compatibility patches to copied SDK files.
        self._patch_sdk_for_aosp(bridge_dir)

        return copied

    @staticmethod
    def _patch_sdk_for_aosp(bridge_dir: Path) -> None:
        """Fix SDK code that fails under AOSP's strict compiler flags.

        AOSP builds with -Werror which catches issues the SDK's original
        toolchain allows. We patch the copies (never the originals).
        """
        com_utils = bridge_dir / "sdk" / "com" / "src" / "com_utils.cpp"
        if com_utils.exists():
            content = com_utils.read_text()
            original = content
            # Fix: uninitialized variable 'idx' triggers
            # -Werror,-Wsometimes-uninitialized
            content = content.replace(
                "uint16_t idx;",
                "uint16_t idx = 0;",
            )
            if content != original:
                com_utils.write_text(content)
                logger.info("Patched SDK: com_utils.cpp (initialized idx)")

        # Fix: clang requires 'template' keyword for dependent name
        # lhs.target<void>() -> lhs.template target<void>()
        s2m_header = bridge_dir / "sdk" / "s2m" / "include" / "signal_to_message.h"
        if s2m_header.exists():
            content = s2m_header.read_text()
            original = content
            content = content.replace(
                "lhs.target<void>()",
                "lhs.template target<void>()",
            )
            content = content.replace(
                "rhs.target<void>()",
                "rhs.template target<void>()",
            )
            if content != original:
                s2m_header.write_text(content)
                logger.info("Patched SDK: signal_to_message.h (template keyword)")

    def _deduplicate_mappings(self) -> list[PropertyMapping]:
        """Return a deduplicated copy of mappings by (property_id, area_id).

        When the same signal name appears in multiple PDUs (e.g.
        ``global_state_value`` in 3 test PDUs), the VendorIdAllocator
        assigns the same property ID.  We keep only the first occurrence.
        """
        seen: set[tuple[int, int]] = set()
        unique: list[PropertyMapping] = []
        for m in self.mappings:
            key = (m.property_id, m.area_id)
            if key in seen:
                logger.debug(
                    "Dedup mapping: %s (prop=0x%08X) from PDU %s",
                    m.signal_name, m.property_id, m.pdu_name,
                )
                continue
            seen.add(key)
            unique.append(m)
        if len(unique) < len(self.mappings):
            logger.info(
                "Deduplicated mappings: %d -> %d",
                len(self.mappings), len(unique),
            )
        return unique

    def _build_signal_entries(self) -> list[dict]:
        """Build signal entry dicts for daemon signal table.

        Deduplicates by (property_id, area_id) so that the same signal
        appearing in multiple PDUs only generates one signal table entry.
        """
        seen: set[tuple[int, int]] = set()
        entries = []
        for m in self.mappings:
            key = (m.property_id, m.area_id)
            if key in seen:
                logger.debug(
                    "Skipping duplicate signal entry: %s (prop=0x%08X, area=%d)",
                    m.signal_name, m.property_id, m.area_id,
                )
                continue
            seen.add(key)
            entries.append({
                "property_id_hex": m.property_id_hex,
                "property_id": m.property_id,
                "area_id": m.area_id,
                "pdu_id": m.pdu_id,
                "start_bit": m.start_bit,
                "bit_length": m.bit_length,
                "bitmask": m.bitmask,
                "is_rx": m.is_rx,
                "signal_name": m.signal_name,
                "vendor_constant_name": m.vendor_constant_name,
                "scale": m.scale,
                "offset": m.offset,
                "convert_kmh_to_ms": m.convert_kmh_to_ms,
                "sdk_getter": m.sdk_getter,
                "sdk_setter": m.sdk_setter,
                "lower_limit": 0,
                "upper_limit": (1 << m.bit_length) - 1,
            })
        return entries

    def _build_pdu_entries(self) -> list[dict]:
        """Build unique PDU entries for daemon."""
        seen = set()
        entries = []
        for m in self.mappings:
            if m.pdu_id not in seen:
                seen.add(m.pdu_id)
                pdu = self._find_pdu(m.pdu_id)
                entries.append({
                    "pdu_id": m.pdu_id,
                    "pdu_id_hex": f"0x{m.pdu_id:X}",
                    "length": pdu.length if pdu else 8,
                    "name": pdu.name if pdu else f"PDU_0x{m.pdu_id:X}",
                    "is_rx": m.is_rx,
                })
        return entries

    def _find_pdu(self, pdu_id: int) -> Optional[PDU]:
        """Find a PDU by ID in the model."""
        for pdu in self.model.pdus.values():
            if pdu.pdu_id == pdu_id:
                return pdu
        return None
