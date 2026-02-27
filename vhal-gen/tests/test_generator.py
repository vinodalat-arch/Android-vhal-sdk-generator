"""Tests for the code generator."""

import json
import shutil
import tempfile
from pathlib import Path

from vhal_gen.classifier.signal_classifier import SignalClassifier
from vhal_gen.generator.generator_engine import GeneratorEngine
from vhal_gen.parser.model_loader import load_flync_model

MODEL_DIR = Path(__file__).parent.parent.parent / "flync-model-dev-2"
SDK_DIR = Path(__file__).parent.parent.parent / "performance-stack-Body-lighting-Draft" / "src"


def _generate_to_tmpdir(sdk_source_dir=None):
    model = load_flync_model(MODEL_DIR)
    classifier = SignalClassifier()
    mappings = classifier.classify(model)
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = GeneratorEngine(
            mappings=mappings, model=model, sdk_source_dir=sdk_source_dir,
        )
        generated = engine.generate(Path(tmpdir))
        return tmpdir, generated, Path(tmpdir)


def test_all_files_generated():
    """Verify all expected output files are generated (without SDK)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        model = load_flync_model(MODEL_DIR)
        classifier = SignalClassifier()
        mappings = classifier.classify(model)
        engine = GeneratorEngine(mappings=mappings, model=model)
        generated = engine.generate(Path(tmpdir))

        assert len(generated) == 13
        filenames = {f.name for f in generated}
        assert "DefaultProperties.json" in filenames
        assert "VendorProperties.h" in filenames
        assert "IpcProtocol.h" in filenames
        assert "BridgeVehicleHardware.h" in filenames
        assert "BridgeVehicleHardware.cpp" in filenames
        assert "VehicleService.cpp" in filenames
        assert "FlyncDaemon.h" in filenames
        assert "FlyncDaemon.cpp" in filenames
        assert "Android.bp" in filenames
        assert "flync-daemon.rc" in filenames
        assert "INTEGRATION.md" in filenames
        assert "VhalTestActivity.java" in filenames
        assert "AndroidManifest.xml" in filenames
        # Transport files should NOT be present
        assert "UdpTransport.h" not in filenames
        assert "UdpTransport.cpp" not in filenames
        assert "MockTransport.h" not in filenames
        assert "MockTransport.cpp" not in filenames


def test_all_files_generated_with_sdk():
    """Verify all output files including SDK copies are generated."""
    if not SDK_DIR.exists():
        return  # Skip if SDK not available
    with tempfile.TemporaryDirectory() as tmpdir:
        model = load_flync_model(MODEL_DIR)
        classifier = SignalClassifier()
        mappings = classifier.classify(model)
        engine = GeneratorEngine(
            mappings=mappings, model=model, sdk_source_dir=SDK_DIR,
        )
        generated = engine.generate(Path(tmpdir))

        # 13 generated + up to 12 SDK files (some may not exist)
        assert len(generated) >= 13
        filenames = {f.name for f in generated}
        assert "Read_App_Signal_Data.h" in filenames
        assert "Write_App_Signal_Data.h" in filenames


def test_sdk_files_copied_verbatim():
    """Verify SDK files are exact copies of the originals."""
    if not SDK_DIR.exists():
        return  # Skip if SDK not available
    with tempfile.TemporaryDirectory() as tmpdir:
        model = load_flync_model(MODEL_DIR)
        classifier = SignalClassifier()
        mappings = classifier.classify(model)
        engine = GeneratorEngine(
            mappings=mappings, model=model, sdk_source_dir=SDK_DIR,
        )
        engine.generate(Path(tmpdir))

        # Check Read_App_Signal_Data.h is an exact copy
        src = SDK_DIR / "app" / "swc" / "Read_App_Signal_Data.h"
        dst = Path(tmpdir) / "vhal" / "sdk" / "app" / "swc" / "Read_App_Signal_Data.h"
        if src.exists():
            assert dst.exists()
            assert src.read_bytes() == dst.read_bytes(), "SDK file was not copied verbatim"


def test_default_properties_valid_json():
    """Verify DefaultProperties.json is valid JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        model = load_flync_model(MODEL_DIR)
        classifier = SignalClassifier()
        mappings = classifier.classify(model)
        engine = GeneratorEngine(mappings=mappings, model=model)
        engine.generate(Path(tmpdir))

        json_path = Path(tmpdir) / "vhal" / "DefaultProperties.json"
        content = json_path.read_text()
        data = json.loads(content)
        assert isinstance(data, dict)
        assert data["apiVersion"] == 1
        assert "properties" in data
        properties = data["properties"]
        assert len(properties) > 0

        # Each entry should have required keys
        for entry in properties:
            assert "property" in entry
            assert "propertyId" in entry
            assert "defaultValue" in entry
            assert "access" in entry
            assert "changeMode" in entry


def test_vendor_properties_header():
    """Verify VendorProperties.h has no duplicate entries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        model = load_flync_model(MODEL_DIR)
        classifier = SignalClassifier()
        mappings = classifier.classify(model)
        engine = GeneratorEngine(mappings=mappings, model=model)
        engine.generate(Path(tmpdir))

        header_path = Path(tmpdir) / "vhal" / "VendorProperties.h"
        content = header_path.read_text()

        # Extract constexpr lines
        constexpr_lines = [
            line.strip()
            for line in content.splitlines()
            if line.strip().startswith("constexpr")
        ]
        # No duplicates
        assert len(constexpr_lines) == len(set(constexpr_lines)), "Duplicate vendor property entries found"


def test_daemon_cpp_has_sdk_includes():
    """Verify FlyncDaemon.cpp includes SDK headers and uses SDK calls."""
    with tempfile.TemporaryDirectory() as tmpdir:
        model = load_flync_model(MODEL_DIR)
        classifier = SignalClassifier()
        mappings = classifier.classify(model)
        engine = GeneratorEngine(mappings=mappings, model=model)
        engine.generate(Path(tmpdir))

        daemon_path = Path(tmpdir) / "vhal" / "FlyncDaemon.cpp"
        content = daemon_path.read_text()
        assert "Read_App_Signal_Data.h" in content
        assert "Write_App_Signal_Data.h" in content
        assert "kSignalTable" in content
        assert "signal_name" in content
        assert "pollRxSignal" in content
        assert "writeTxSignal" in content
        # No custom bit manipulation
        assert "extractBits" not in content
        assert "packBits" not in content


def test_daemon_h_has_signal_binding():
    """Verify FlyncDaemon.h uses SignalBinding instead of SignalDescriptor."""
    with tempfile.TemporaryDirectory() as tmpdir:
        model = load_flync_model(MODEL_DIR)
        classifier = SignalClassifier()
        mappings = classifier.classify(model)
        engine = GeneratorEngine(mappings=mappings, model=model)
        engine.generate(Path(tmpdir))

        header_path = Path(tmpdir) / "vhal" / "FlyncDaemon.h"
        content = header_path.read_text()
        assert "SignalBinding" in content
        assert "SignalDescriptor" not in content
        assert "ITransport" not in content
        assert "extractBits" not in content
        assert "packBits" not in content


def test_bridge_aosp_compatibility():
    """Verify BridgeVehicleHardware uses correct AOSP namespace and interface."""
    with tempfile.TemporaryDirectory() as tmpdir:
        model = load_flync_model(MODEL_DIR)
        classifier = SignalClassifier()
        mappings = classifier.classify(model)
        engine = GeneratorEngine(mappings=mappings, model=model)
        engine.generate(Path(tmpdir))

        # Check header uses correct namespace (not HIDL-era V2_0)
        header = (Path(tmpdir) / "vhal" / "BridgeVehicleHardware.h").read_text()
        assert "namespace android::hardware::automotive::vehicle::bridge" in header
        assert "V2_0" not in header, "Should not use HIDL-era V2_0 namespace"
        assert "IVehicleHardware" in header
        assert "getValues" in header
        assert "const override" in header  # getValues must be const

        # Check cpp uses AIDL enum types (not raw int casts)
        cpp = (Path(tmpdir) / "vhal" / "BridgeVehicleHardware.cpp").read_text()
        assert "namespace android::hardware::automotive::vehicle::bridge" in cpp
        assert "VehiclePropertyAccess::READ" in cpp
        assert "VehiclePropertyChangeMode::ON_CHANGE" in cpp
        assert "static_cast<int32_t>(0x" not in cpp, \
            "Should not use raw int casts for access/changeMode"

        # Check VehicleService.cpp matches AOSP patterns
        svc = (Path(tmpdir) / "vhal" / "VehicleService.cpp").read_text()
        assert "BridgeVehicleHardware" in svc
        assert "DefaultVehicleHal" in svc
        assert "binder_exception_t" in svc, "Should use binder_exception_t, not binder_status_t"
        assert "ALOGI" in svc, "Should use ALOGI to match AOSP style"
        assert "IVehicle/default" in svc

        # Check Android.bp has SDK sources and NO transport references
        bp = (Path(tmpdir) / "vhal" / "Android.bp").read_text()
        assert "BridgeVehicleHardware" in bp
        assert "flync-daemon" in bp
        assert "prebuilt_etc" in bp
        assert "VehicleHalDefaults" in bp
        assert "@V1" not in bp, "Should not hardcode AIDL version"
        assert "@V3" not in bp, "Should not hardcode AIDL version"
        assert "vehicle-V3-ndk" not in bp, "Should not hardcode AIDL NDK lib version"
        assert "sdk/com/src/ComConfig.cpp" in bp
        assert "sdk/app/swc/Read_App_Signal_Data.cpp" in bp
        assert "UdpTransport" not in bp
        assert "MockTransport" not in bp

        # Check integration guide is generated
        guide = (Path(tmpdir) / "vhal" / "INTEGRATION.md").read_text()
        assert "FakeVehicleHardware" in guide
        assert "BridgeVehicleHardware" in guide
        assert "Vehicle Body SDK" in guide
