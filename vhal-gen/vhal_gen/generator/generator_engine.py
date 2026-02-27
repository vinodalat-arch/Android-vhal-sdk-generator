"""Orchestrator for code generation from classified signal mappings."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader

from ..models.signal import FlyncModel, PDU
from ..models.vehicle_property import PropertyMapping

logger = logging.getLogger(__name__)

# Template directory relative to this file
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


class GeneratorEngine:
    """Generates all output files from FLYNC model and signal mappings."""

    def __init__(
        self,
        mappings: list[PropertyMapping],
        model: FlyncModel,
        transport: str = "mock",
        udp_addr: str = "10.0.11.1",
        udp_port: int = 5555,
    ):
        self.mappings = mappings
        self.model = model
        self.transport = transport
        self.udp_addr = udp_addr
        self.udp_port = udp_port
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
            "transport": self.transport,
            "udp_addr": self.udp_addr,
            "udp_port": self.udp_port,
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
            ("UdpTransport.h.j2", vhal_dir / "UdpTransport.h"),
            ("UdpTransport.cpp.j2", vhal_dir / "UdpTransport.cpp"),
            ("MockTransport.h.j2", vhal_dir / "MockTransport.h"),
            ("MockTransport.cpp.j2", vhal_dir / "MockTransport.cpp"),
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

        return generated

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
