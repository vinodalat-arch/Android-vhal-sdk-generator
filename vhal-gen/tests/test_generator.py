"""Tests for the code generator — generates into a mock VHAL tree."""

import json
import shutil
import tempfile
from pathlib import Path

from vhal_gen.classifier.signal_classifier import SignalClassifier
from vhal_gen.generator.generator_engine import GeneratorEngine
from vhal_gen.parser.model_loader import load_flync_model

MODEL_DIR = Path(__file__).parent.parent.parent / "flync-model-dev-2"
SDK_DIR = Path(__file__).parent.parent.parent / "performance-stack-Body-lighting-Draft" / "src"

# ── Stock AOSP content used to build the mock VHAL tree ──

STOCK_VEHICLE_SERVICE_CPP = """\
/*
 * Copyright (C) 2021 The Android Open Source Project
 */

#define LOG_TAG "VehicleService"

#include <DefaultVehicleHal.h>
#include <FakeVehicleHardware.h>

#include <android/binder_manager.h>
#include <android/binder_process.h>
#include <utils/Log.h>

using ::android::hardware::automotive::vehicle::DefaultVehicleHal;
using ::android::hardware::automotive::vehicle::fake::FakeVehicleHardware;

int main(int /* argc */, char* /* argv */[]) {
    ALOGI("Starting thread pool...");
    if (!ABinderProcess_setThreadPoolMaxThreadCount(4)) {
        ALOGE("Failed to set thread pool max thread count");
        return 1;
    }
    ABinderProcess_startThreadPool();

    std::unique_ptr<FakeVehicleHardware> hardware = std::make_unique<FakeVehicleHardware>();
    std::shared_ptr<DefaultVehicleHal> vhal =
            ::ndk::SharedRefBase::make<DefaultVehicleHal>(std::move(hardware));

    ALOGI("VHAL service starting...");
    binder_status_t status = AServiceManager_addService(
            vhal->asBinder().get(),
            "android.hardware.automotive.vehicle.IVehicle/default");
    if (status != STATUS_OK) {
        ALOGE("Failed to add VHAL service");
        return 1;
    }

    ALOGI("VHAL service ready");
    ABinderProcess_joinThreadPool();
    return 0;
}
"""

STOCK_VHAL_ANDROID_BP = """\
package {
    default_applicable_licenses: ["Android-Apache-2.0"],
}

cc_binary {
    name: "android.hardware.automotive.vehicle@V1-default-service",
    vendor: true,
    defaults: [
        "FakeVehicleHardwareDefaults",
        "VehicleHalDefaults",
        "android-automotive-large-parcelable-defaults",
    ],
    vintf_fragments: ["vhal-default-service.xml"],
    init_rc: ["vhal-default-service.rc"],
    relative_install_path: "hw",
    srcs: ["src/VehicleService.cpp"],
    static_libs: [
        "DefaultVehicleHal",
        "FakeVehicleHardware",
        "VehicleHalUtils",
    ],
    shared_libs: [
        "libbinder_ndk",
    ],
    header_libs: [
        "IVehicleHardware",
    ],
}

cc_library {
    name: "DefaultVehicleHal",
    vendor: true,
    defaults: [
        "VehicleHalDefaults",
    ],
    static_libs: [
        "VehicleHalUtils",
    ],
    shared_libs: [
        "libbinder_ndk",
    ],
}

cc_fuzz {
    name: "android.hardware.automotive.vehicle-default-service_fuzzer",
    vendor: true,
    defaults: [
        "FakeVehicleHardwareDefaults",
        "VehicleHalDefaults",
        "service_fuzzer_defaults",
    ],
    static_libs: [
        "DefaultVehicleHal",
        "FakeVehicleHardware",
        "VehicleHalUtils",
    ],
    srcs: ["src/fuzzer.cpp"],
}
"""


def _build_mock_vhal_tree(tmpdir: Path) -> Path:
    """Create a minimal mock VHAL tree and return vhal_root path."""
    vhal_root = tmpdir / "automotive" / "vehicle" / "aidl"

    # Create stock VehicleService.cpp
    vs_dir = vhal_root / "impl" / "vhal" / "src"
    vs_dir.mkdir(parents=True)
    (vs_dir / "VehicleService.cpp").write_text(STOCK_VEHICLE_SERVICE_CPP)

    # Create stock vhal/Android.bp
    bp_dir = vhal_root / "impl" / "vhal"
    (bp_dir / "Android.bp").write_text(STOCK_VHAL_ANDROID_BP)

    return vhal_root


def _generate_into_mock_tree(sdk_source_dir=None):
    """Helper: build mock tree, generate into it, return (vhal_root, generated)."""
    model = load_flync_model(MODEL_DIR)
    classifier = SignalClassifier()
    mappings = classifier.classify(model)

    tmpdir = Path(tempfile.mkdtemp())
    vhal_root = _build_mock_vhal_tree(tmpdir)

    engine = GeneratorEngine(
        mappings=mappings, model=model, sdk_source_dir=sdk_source_dir,
    )
    generated = engine.generate(vhal_root=vhal_root)
    return tmpdir, vhal_root, generated


def test_all_files_generated():
    """Verify all expected output files are generated in impl/bridge/."""
    tmpdir, vhal_root, generated = _generate_into_mock_tree()
    try:
        assert len(generated) == 13
        filenames = {f.name for f in generated}
        assert "DefaultProperties.json" in filenames
        assert "VendorProperties.h" in filenames
        assert "IpcProtocol.h" in filenames
        assert "BridgeVehicleHardware.h" in filenames
        assert "BridgeVehicleHardware.cpp" in filenames
        assert "VehicleDaemon.h" in filenames
        assert "VehicleDaemon.cpp" in filenames
        assert "Android.bp" in filenames
        assert "INTEGRATION.md" in filenames
        assert "VhalTestActivity.java" in filenames
        assert "AndroidManifest.xml" in filenames
        # rc file should NOT be generated (daemon is child process)
        assert "vehicle-daemon.rc" not in filenames
        # Patch file should NOT be generated
        assert "VehicleService.cpp.patch" not in filenames
        # Transport files should NOT be present
        assert "UdpTransport.h" not in filenames
        assert "UdpTransport.cpp" not in filenames

        # All files should be under impl/bridge/
        bridge_dir = vhal_root / "impl" / "bridge"
        for f in generated:
            assert str(f).startswith(str(bridge_dir)), f"{f} not under {bridge_dir}"
    finally:
        shutil.rmtree(tmpdir)


def test_all_files_generated_with_sdk():
    """Verify all output files including SDK copies are generated."""
    if not SDK_DIR.exists():
        return  # Skip if SDK not available
    tmpdir, vhal_root, generated = _generate_into_mock_tree(sdk_source_dir=SDK_DIR)
    try:
        # 11 generated + up to 12 SDK files (some may not exist)
        assert len(generated) >= 11
        filenames = {f.name for f in generated}
        assert "Read_App_Signal_Data.h" in filenames
        assert "Write_App_Signal_Data.h" in filenames
    finally:
        shutil.rmtree(tmpdir)


def test_sdk_files_copied_verbatim():
    """Verify SDK files are exact copies of the originals."""
    if not SDK_DIR.exists():
        return  # Skip if SDK not available
    tmpdir, vhal_root, _ = _generate_into_mock_tree(sdk_source_dir=SDK_DIR)
    try:
        src = SDK_DIR / "app" / "swc" / "Read_App_Signal_Data.h"
        dst = vhal_root / "impl" / "bridge" / "sdk" / "app" / "swc" / "Read_App_Signal_Data.h"
        if src.exists():
            assert dst.exists()
            assert src.read_bytes() == dst.read_bytes(), "SDK file was not copied verbatim"
    finally:
        shutil.rmtree(tmpdir)


def test_vehicle_service_cpp_patched():
    """Verify VehicleService.cpp is modified in-place to use BridgeVehicleHardware."""
    tmpdir, vhal_root, _ = _generate_into_mock_tree()
    try:
        vs_path = vhal_root / "impl" / "vhal" / "src" / "VehicleService.cpp"
        content = vs_path.read_text()

        # BridgeVehicleHardware should be present
        assert "BridgeVehicleHardware" in content
        assert "#include <BridgeVehicleHardware.h>" in content
        assert "bridge::BridgeVehicleHardware" in content
        assert "std::make_unique<BridgeVehicleHardware>()" in content

        # FakeVehicleHardware should be completely gone
        assert "FakeVehicleHardware" not in content
    finally:
        shutil.rmtree(tmpdir)


def test_vhal_android_bp_modified():
    """Verify vhal/Android.bp cc_binary block is modified, others untouched."""
    tmpdir, vhal_root, _ = _generate_into_mock_tree()
    try:
        bp_path = vhal_root / "impl" / "vhal" / "Android.bp"
        content = bp_path.read_text()

        # --- cc_binary block should be modified ---
        # BridgeVehicleHardware should replace FakeVehicleHardware in cc_binary
        assert '"BridgeVehicleHardware"' in content

        # libjsoncpp should be added to cc_binary shared_libs
        assert '"libjsoncpp"' in content

        # required for DefaultProperties.json and vehicle-daemon
        assert '"vehicle-DefaultProperties.json"' in content
        assert '"vehicle-daemon"' in content

        # Original binary name should be preserved
        assert "android.hardware.automotive.vehicle@V1-default-service" in content

        # --- cc_library block should be UNTOUCHED ---
        # cc_library (DefaultVehicleHal) should not have libjsoncpp or required added
        # Split by block to check individually
        cc_lib_start = content.index("cc_library {")
        cc_lib_section = content[cc_lib_start:]
        cc_lib_end = cc_lib_section.index("\n}\n") + 3
        cc_lib_block = cc_lib_section[:cc_lib_end]
        assert '"libjsoncpp"' not in cc_lib_block, "cc_library should not have libjsoncpp"
        assert "vehicle-DefaultProperties" not in cc_lib_block, "cc_library should not have required"

        # --- cc_fuzz block should be UNTOUCHED ---
        cc_fuzz_start = content.index("cc_fuzz {")
        cc_fuzz_block = content[cc_fuzz_start:]
        assert '"FakeVehicleHardware"' in cc_fuzz_block, "cc_fuzz should keep FakeVehicleHardware"
        assert "FakeVehicleHardwareDefaults" in cc_fuzz_block, "cc_fuzz should keep FakeVehicleHardwareDefaults"
    finally:
        shutil.rmtree(tmpdir)


def test_default_properties_valid_json():
    """Verify DefaultProperties.json is valid JSON."""
    tmpdir, vhal_root, _ = _generate_into_mock_tree()
    try:
        json_path = vhal_root / "impl" / "bridge" / "DefaultProperties.json"
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
    finally:
        shutil.rmtree(tmpdir)


def test_vendor_properties_header():
    """Verify VendorProperties.h has no duplicate entries."""
    tmpdir, vhal_root, _ = _generate_into_mock_tree()
    try:
        header_path = vhal_root / "impl" / "bridge" / "VendorProperties.h"
        content = header_path.read_text()

        # Extract constexpr lines
        constexpr_lines = [
            line.strip()
            for line in content.splitlines()
            if line.strip().startswith("constexpr")
        ]
        # No duplicates
        assert len(constexpr_lines) == len(set(constexpr_lines)), "Duplicate vendor property entries found"
    finally:
        shutil.rmtree(tmpdir)


def test_daemon_cpp_has_sdk_includes():
    """Verify VehicleDaemon.cpp includes SDK headers and uses SDK calls."""
    tmpdir, vhal_root, _ = _generate_into_mock_tree()
    try:
        daemon_path = vhal_root / "impl" / "bridge" / "VehicleDaemon.cpp"
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
    finally:
        shutil.rmtree(tmpdir)


def test_daemon_h_has_signal_binding():
    """Verify VehicleDaemon.h uses SignalBinding instead of SignalDescriptor."""
    tmpdir, vhal_root, _ = _generate_into_mock_tree()
    try:
        header_path = vhal_root / "impl" / "bridge" / "VehicleDaemon.h"
        content = header_path.read_text()
        assert "SignalBinding" in content
        assert "SignalDescriptor" not in content
        assert "ITransport" not in content
        assert "extractBits" not in content
        assert "packBits" not in content
    finally:
        shutil.rmtree(tmpdir)


def test_bridge_aosp_compatibility():
    """Verify BridgeVehicleHardware uses correct AOSP namespace and interface."""
    tmpdir, vhal_root, _ = _generate_into_mock_tree()
    try:
        bridge_dir = vhal_root / "impl" / "bridge"

        # Check header uses correct namespace (not HIDL-era V2_0)
        header = (bridge_dir / "BridgeVehicleHardware.h").read_text()
        assert "namespace android::hardware::automotive::vehicle::bridge" in header
        assert "V2_0" not in header, "Should not use HIDL-era V2_0 namespace"
        assert "IVehicleHardware" in header
        assert "getValues" in header
        assert "const override" in header  # getValues must be const

        # Check cpp uses AIDL enum types (not raw int casts)
        cpp = (bridge_dir / "BridgeVehicleHardware.cpp").read_text()
        assert "namespace android::hardware::automotive::vehicle::bridge" in cpp
        assert "VehiclePropertyAccess::READ" in cpp
        assert "VehiclePropertyChangeMode::ON_CHANGE" in cpp
        assert "static_cast<int32_t>(0x" not in cpp, \
            "Should not use raw int casts for access/changeMode"

        # Check Android.bp has package declaration, SDK sources, NO transport references
        bp = (bridge_dir / "Android.bp").read_text()
        assert 'default_applicable_licenses' in bp, "Missing package {} block"
        assert "BridgeVehicleHardware" in bp
        assert "vehicle-daemon" in bp
        assert "prebuilt_etc" in bp
        assert "VehicleHalDefaults" in bp
        assert "@V1" not in bp, "Should not hardcode AIDL version"
        assert "@V3" not in bp, "Should not hardcode AIDL version"
        assert "vehicle-V3-ndk" not in bp, "Should not hardcode AIDL NDK lib version"
        assert "sdk/com/src/ComConfig.cpp" in bp
        assert "sdk/app/swc/Read_App_Signal_Data.cpp" in bp
        assert "UdpTransport" not in bp
        assert "MockTransport" not in bp
        assert "init_rc" not in bp, "Daemon is child process, no init_rc needed"

        # Check BridgeVehicleHardware.cpp uses socketpair/fork/exec
        assert "socketpair" in cpp
        assert "fork()" in cpp
        assert "execl" in cpp
        assert "prctl" in cpp

        # Check integration guide is generated
        guide = (bridge_dir / "INTEGRATION.md").read_text()
        assert "BridgeVehicleHardware" in guide
        assert "Vehicle Body SDK" in guide
    finally:
        shutil.rmtree(tmpdir)
