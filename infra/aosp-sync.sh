#!/usr/bin/env bash
# Selective AOSP repo sync — only the repos required to build VHAL modules.
#
# Syncs ~80 GB (vs ~300 GB for a full tree).
#
# Usage:
#   bash infra/aosp-sync.sh [AOSP_TAG] [AOSP_DIR]
#
# Defaults:
#   AOSP_TAG = android-14.0.0_r75
#   AOSP_DIR = /aosp

set -euo pipefail

AOSP_TAG="${1:-android-14.0.0_r75}"
AOSP_DIR="${2:-/aosp}"

# Repos required for `m android.hardware.automotive.vehicle@V3-default-service`
SYNC_GROUPS=(
    # VHAL module itself
    "hardware/interfaces"
    # Core frameworks
    "frameworks/native"
    "frameworks/base"
    "system/core"
    "system/libbase"
    "system/logging"
    "system/tools/aidl"
    # Build system
    "build/make"
    "build/soong"
    "build/bazel"
    "build/blueprint"
    # Prebuilts (compiler toolchains)
    "prebuilts/clang/host/linux-x86"
    "prebuilts/gcc/linux-x86/x86/x86_64-linux-android-4.9"
    "prebuilts/build-tools"
    "prebuilts/go/linux-x86"
    # Needed by soong/build
    "external/golang-protobuf"
    "external/protobuf"
    "external/jsoncpp"
    "external/googletest"
    # Binder / AIDL / HIDL
    "frameworks/av"
    "packages/modules/Bluetooth"
    "system/tools/hidl"
    # Automotive
    "packages/services/Car"
)

echo "==> Initializing AOSP repo in ${AOSP_DIR} (tag: ${AOSP_TAG})"
mkdir -p "${AOSP_DIR}"
cd "${AOSP_DIR}"

repo init \
    -u https://android.googlesource.com/platform/manifest \
    -b "${AOSP_TAG}" \
    --depth=1

echo "==> Selective sync of ${#SYNC_GROUPS[@]} repo groups..."
# Use repo sync with specific project paths for selective sync.
# --current-branch + --depth=1 keeps download size small.
repo sync \
    --current-branch \
    --no-tags \
    --optimized-fetch \
    --prune \
    --jobs="$(nproc)" \
    "${SYNC_GROUPS[@]}"

echo "==> Sync complete.  Disk usage:"
du -sh "${AOSP_DIR}"

echo ""
echo "==> To build VHAL, run:"
echo "    cd ${AOSP_DIR}"
echo "    source build/envsetup.sh"
echo "    lunch sdk_car_x86_64-userdebug"
echo "    m android.hardware.automotive.vehicle@V3-default-service flync-daemon"
