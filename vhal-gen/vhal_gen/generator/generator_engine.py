"""Orchestrator for code generation from classified signal mappings."""

from __future__ import annotations

import logging
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
# under output/vhal/sdk/.
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

    def generate(self, output_dir: Path) -> list[Path]:
        """Generate all output files to the specified directory.

        Returns list of generated file paths.
        """
        vhal_dir = output_dir / "vhal"
        test_dir = output_dir / "vhal" / "test-apk"
        vhal_dir.mkdir(parents=True, exist_ok=True)
        test_dir.mkdir(parents=True, exist_ok=True)

        generated = []

        vendor_mappings = [m for m in self.mappings if m.is_vendor]
        standard_mappings = [m for m in self.mappings if m.is_standard]

        # Build signal entries for daemon templates
        signal_entries = self._build_signal_entries()
        pdu_entries = self._build_pdu_entries()

        # Context shared across templates
        ctx = {
            "mappings": self.mappings,
            "vendor_mappings": vendor_mappings,
            "standard_mappings": standard_mappings,
            "signal_entries": signal_entries,
            "pdu_entries": pdu_entries,
            "config_json_path": "/vendor/etc/automotive/vhal/DefaultProperties.json",
        }

        # Files to generate: (template_name, output_path)
        file_map = [
            ("DefaultProperties.json.j2", vhal_dir / "DefaultProperties.json"),
            ("VendorProperties.h.j2", vhal_dir / "VendorProperties.h"),
            ("IpcProtocol.h.j2", vhal_dir / "IpcProtocol.h"),
            ("BridgeVehicleHardware.h.j2", vhal_dir / "BridgeVehicleHardware.h"),
            ("BridgeVehicleHardware.cpp.j2", vhal_dir / "BridgeVehicleHardware.cpp"),
            ("VehicleService.cpp.j2", vhal_dir / "VehicleService.cpp"),
            ("FlyncDaemon.h.j2", vhal_dir / "FlyncDaemon.h"),
            ("FlyncDaemon.cpp.j2", vhal_dir / "FlyncDaemon.cpp"),
            ("Android.bp.j2", vhal_dir / "Android.bp"),
            ("flync-daemon.rc.j2", vhal_dir / "flync-daemon.rc"),
            ("INTEGRATION.md.j2", vhal_dir / "INTEGRATION.md"),
            ("VhalTestActivity.java.j2", test_dir / "VhalTestActivity.java"),
            ("AndroidManifest.xml.j2", test_dir / "AndroidManifest.xml"),
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
            sdk_files = self._copy_sdk_files(vhal_dir)
            generated.extend(sdk_files)

        return generated

    def _copy_sdk_files(self, vhal_dir: Path) -> list[Path]:
        """Copy Vehicle Body SDK files verbatim into the output directory.

        Returns list of copied file paths.
        """
        copied = []
        for src_rel, dst_rel in SDK_FILE_MAP.items():
            src_path = self.sdk_source_dir / src_rel
            dst_path = vhal_dir / dst_rel
            dst_path.parent.mkdir(parents=True, exist_ok=True)

            if not src_path.exists():
                logger.warning("SDK file not found: %s", src_path)
                continue

            shutil.copy2(src_path, dst_path)
            copied.append(dst_path)
            logger.info("Copied SDK: %s -> %s", src_path, dst_path)

        return copied

    def _build_signal_entries(self) -> list[dict]:
        """Build signal entry dicts for daemon signal table."""
        entries = []
        for m in self.mappings:
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
