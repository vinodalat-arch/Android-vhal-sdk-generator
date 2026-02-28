"""Constants for the deploy-test pipeline."""

from __future__ import annotations

# GitHub Actions
WORKFLOW_FILE = "build-vhal.yml"
DEFAULT_AOSP_TAG = "android-14.0.0_r75"
DEFAULT_BUILD_TARGET = "sdk_car_x86_64-trunk_staging-userdebug"
BUILD_TIMEOUT_SECONDS = 2 * 60 * 60  # 2 hours
BUILD_POLL_INTERVAL_SECONDS = 30

# Artifact files expected from the build
ARTIFACT_FILES = [
    "android.hardware.automotive.vehicle@V3-default-service",
    "flync-daemon",
    "flync-DefaultProperties.json",
    "build-info.json",
]

# Device paths for adb push
DEVICE_VHAL_SERVICE_DIR = "/vendor/bin/hw"
DEVICE_DAEMON_DIR = "/vendor/bin"
DEVICE_CONFIG_DIR = "/vendor/etc/automotive/vhal"

DEVICE_PATHS = {
    "android.hardware.automotive.vehicle@V3-default-service": (
        f"{DEVICE_VHAL_SERVICE_DIR}/android.hardware.automotive.vehicle@V3-default-service"
    ),
    "flync-daemon": f"{DEVICE_DAEMON_DIR}/flync-daemon",
    "flync-DefaultProperties.json": (
        f"{DEVICE_CONFIG_DIR}/flync-DefaultProperties.json"
    ),
}

# SELinux context for binaries
SELINUX_CONTEXT = "u:object_r:hal_vehicle_default_exec:s0"

# Service names for stop/start
VHAL_SERVICE_NAME = "vendor.vehicle-hal-default"

# Artifact download
ARTIFACT_DOWNLOAD_RETRIES = 3
ARTIFACT_DOWNLOAD_BACKOFF_SECONDS = 10

# adb
ADB_REBOOT_WAIT_SECONDS = 60

# GCP Incremental Build
GCP_REMOTE_VHAL_PATH = "~/aosp/hardware/interfaces/automotive/vehicle/aidl/impl/bridge"
GCP_REMOTE_BUILD_PATH = "~/aosp/hardware/interfaces/automotive/vehicle/aidl/impl/vhal"
GCP_PRODUCT_OUT_PATH = "~/aosp/out/target/product/emulator_car64_x86_64"
GCP_INCREMENTAL_BUILD_TIMEOUT = 20 * 60  # 20 minutes
GCP_ARTIFACT_REMOTE_PATHS = {
    "android.hardware.automotive.vehicle@V3-default-service": (
        "vendor/bin/hw/android.hardware.automotive.vehicle@V3-default-service"
    ),
    "flync-daemon": "vendor/bin/flync-daemon",
    "flync-DefaultProperties.json": (
        "vendor/etc/automotive/vhal/flync-DefaultProperties.json"
    ),
}
