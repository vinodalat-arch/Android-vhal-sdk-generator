"""Constants for the deploy-test pipeline."""

from __future__ import annotations

import platform

# Auto-detect host architecture → pick matching AOSP lunch target
_MACHINE = platform.machine()  # "x86_64" or "arm64"/"aarch64"
if _MACHINE == "x86_64":
    _ARCH_LUNCH = "sdk_car_x86_64-trunk_staging-userdebug"
    _ARCH_PRODUCT = "emulator_car_x86_64"
else:
    _ARCH_LUNCH = "sdk_car_arm64-trunk_staging-userdebug"
    _ARCH_PRODUCT = "emulator_car64_arm64"

# Build
WORKFLOW_FILE = "build-vhal.yml"
DEFAULT_AOSP_TAG = "android-14.0.0_r75"
DEFAULT_BUILD_TARGET = _ARCH_LUNCH
DEFAULT_LUNCH_TARGET = _ARCH_LUNCH
BUILD_TIMEOUT_SECONDS = 2 * 60 * 60  # 2 hours
BUILD_POLL_INTERVAL_SECONDS = 30

# VHAL binary name produced by the GCP AOSP build
VHAL_SERVICE_BINARY = "android.hardware.automotive.vehicle@V3-default-service"

# Stock Google AVD ships a different binary name (V1) and service name.
# Deploy replaces the stock binary and updates the VINTF manifest so init
# picks up our V3 binary under the stock service name.
DEVICE_VHAL_BINARY_NAME = "android.hardware.automotive.vehicle@V1-emulator-service"
DEVICE_VHAL_SERVICE_NAME_EMU = "vendor.vehicle-hal-emulator"

# Artifact files expected from the GCP build
ARTIFACT_FILES = [
    VHAL_SERVICE_BINARY,
    "DefaultProperties.json",
    "vehicle-daemon",
    "DefaultVehicleHal.so",
    "build-info.json",
]

# Device paths for adb push — maps local artifact name → device destination.
# The VHAL binary is pushed under the stock binary name so init.rc picks it up
# without needing to modify the init script.
DEVICE_VHAL_SERVICE_DIR = "/vendor/bin/hw"
DEVICE_CONFIG_DIR = "/vendor/etc/automotive/vhal"
DEVICE_VINTF_DIR = "/vendor/etc/vintf/manifest"

DEVICE_PATHS = {
    VHAL_SERVICE_BINARY: (
        f"{DEVICE_VHAL_SERVICE_DIR}/{DEVICE_VHAL_BINARY_NAME}"
    ),
    "vehicle-daemon": "/vendor/bin/vehicle-daemon",
    "DefaultVehicleHal.so": "/vendor/lib64/DefaultVehicleHal.so",
    "VhalTestApp.apk": "/system/priv-app/VhalTestApp/VhalTestApp.apk",
}

# Test app package and activity for launch after deploy
TEST_APP_PACKAGE = "com.vehicle.vhaltest"
TEST_APP_ACTIVITY = "com.vehicle.vhaltest/.VhalTestActivity"

# VINTF manifest to push — upgrades the stock V2 declaration to V3
# so the framework accepts our V3 VHAL service.
DEVICE_VINTF_MANIFEST_PATH = f"{DEVICE_VINTF_DIR}/vhal-emulator-service.xml"
VINTF_MANIFEST_V3 = """\
<manifest version="1.0" type="device">
    <hal format="aidl">
        <name>android.hardware.automotive.vehicle</name>
        <version>3</version>
        <fqname>IVehicle/default</fqname>
    </hal>
</manifest>
"""

# SELinux context for binaries
SELINUX_CONTEXT = "u:object_r:hal_vehicle_default_exec:s0"

# Service names for stop/start on stock emulator
VHAL_SERVICE_NAME = "vendor.vehicle-hal-emulator"

# Artifact download
ARTIFACT_DOWNLOAD_RETRIES = 3
ARTIFACT_DOWNLOAD_BACKOFF_SECONDS = 10

# adb
ADB_REBOOT_WAIT_SECONDS = 60

# Emulator UDP port forwarding for VSM Ethernet communication
# Maps host UDP port → guest UDP port so external VSM hardware can
# send/receive packets to the vehicle-daemon inside the emulator.
EMULATOR_UDP_FORWARD_PORT = 5555

# GCP Incremental Build
GCP_REMOTE_VHAL_PATH = "~/aosp/hardware/interfaces/automotive/vehicle/aidl/impl/bridge"
GCP_REMOTE_BUILD_PATH = "~/aosp/hardware/interfaces/automotive/vehicle/aidl/impl/vhal"
GCP_PRODUCT_OUT_PATH = f"~/aosp/out/target/product/{_ARCH_PRODUCT}"
GCP_INCREMENTAL_BUILD_TIMEOUT = 20 * 60  # 20 minutes
GCP_ARTIFACT_REMOTE_PATHS = {
    VHAL_SERVICE_BINARY: (
        f"vendor/bin/hw/{VHAL_SERVICE_BINARY}"
    ),
    "vehicle-daemon": "vendor/bin/vehicle-daemon",
    "DefaultVehicleHal.so": "vendor/lib64/DefaultVehicleHal.so",
    "VhalTestApp.apk": "system/priv-app/VhalTestApp/VhalTestApp.apk",
}

# Generated files that change every run (sync only these, not SDK)
GCP_GENERATED_BRIDGE_FILES = [
    "DefaultProperties.json", "VendorProperties.h", "IpcProtocol.h",
    "BridgeVehicleHardware.h", "BridgeVehicleHardware.cpp",
    "VehicleDaemon.h", "VehicleDaemon.cpp",
    "Android.bp", "INTEGRATION.md", "iceoryx2_stubs.cpp",
    "privapp-permissions-vhaltest.xml",
    "test-apk/VhalTestActivity.java", "test-apk/AndroidManifest.xml",
]
