# VHAL SDK Generator

Generates Android Vehicle Hardware Abstraction Layer (VHAL) bridge code from FLYNC YAML signal models. The generated code connects an AOSP VHAL service to a Vehicle Body SDK via a daemon process that communicates over a socketpair.

## Architecture

```
Vehicle Network (UDP)
        |
┌──────────────────────────────────────────┐
│  Vehicle Body SDK (sdk/ directory)       │
│  com/     -> signal pack/unpack          │
│  can_io/  -> wire format                 │
│  app/swc/ -> get_*() / set_*() API       │
└──────────────┬───────────────────────────┘
               | SDK API calls
┌──────────────────────────────────────────┐
│  VehicleDaemon (child process of VHAL)   │
│  - Spawned via fork()+exec()             │
│  - Communicates over socketpair          │
│  - Polls SDK get_*() for RX signals      │
│  - Calls SDK set_*() for TX signals      │
└──────────────┬───────────────────────────┘
               | socketpair IPC
┌──────────────────────────────────────────┐
│  BridgeVehicleHardware (IVehicleHardware)│
│  - Replaces FakeVehicleHardware          │
│  - Watchdog: auto-respawns daemon        │
│  - Android CarService consumes this      │
└──────────────────────────────────────────┘
```

## Prerequisites

### Ubuntu 22.04 Setup

```bash
# System packages
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3-pip git clang

# Clone the repository
git clone <repo-url> && cd Android-vhal-sdk-generator

# Python virtual environment
cd vhal-gen
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### macOS Setup

```bash
# Install Homebrew packages
brew install python@3.10 llvm

# Clone and setup
git clone <repo-url> && cd Android-vhal-sdk-generator
cd vhal-gen
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Required Inputs

1. **FLYNC Model Directory** — YAML files defining PDUs, signals, and channels
2. **AOSP VHAL Source Tree** — `hardware/interfaces/automotive/vehicle/aidl/` from an Android 14 AOSP checkout
3. **Vehicle Body SDK** (optional) — `performance-stack-Body-lighting-Draft/src/` for full daemon build

## Quick Start

### 1. Inspect Model

```bash
vhal-gen inspect /path/to/flync-model
```

### 2. Classify Signals

```bash
vhal-gen classify /path/to/flync-model
```

### 3. Generate Code

```bash
vhal-gen generate /path/to/flync-model \
    --vhal-dir /path/to/aosp/hardware/interfaces/automotive/vehicle/aidl \
    --sdk-dir /path/to/performance-stack-Body-lighting-Draft/src
```

This generates 13 files into `impl/bridge/`:
- `BridgeVehicleHardware.h` / `.cpp` — IVehicleHardware implementation
- `VehicleDaemon.h` / `.cpp` — daemon with SDK signal dispatchers
- `IpcProtocol.h` — binary IPC protocol
- `VendorProperties.h` — vendor property ID constants
- `DefaultProperties.json` — property configs (AOSP format)
- `Android.bp` — build rules for bridge + daemon + test app
- `iceoryx2_stubs.cpp` — iceoryx2 runtime stubs for Android
- `INTEGRATION.md` — integration guide
- `VhalTestActivity.java` / `AndroidManifest.xml` — test app
- `privapp-permissions-vhaltest.xml` — privileged app permissions allowlist

It also modifies:
- `impl/vhal/src/VehicleService.cpp` — replaces FakeVehicleHardware with BridgeVehicleHardware
- `impl/vhal/Android.bp` — adds BridgeVehicleHardware and libjsoncpp dependencies

### 4. Compile Check (local, no AOSP required)

```bash
vhal-gen compile-check \
    --vhal-dir /path/to/aosp/hardware/interfaces/automotive/vehicle/aidl \
    --sdk-dir /path/to/performance-stack-Body-lighting-Draft/src
```

Uses stub AOSP headers for a syntax-only `clang++` check on macOS/Linux.

### 5. Full Pipeline (Generate + Check)

```bash
vhal-gen test /path/to/flync-model \
    --vhal-dir /path/to/aosp/hardware/interfaces/automotive/vehicle/aidl \
    --sdk-dir /path/to/performance-stack-Body-lighting-Draft/src
```

## GCP Build & Deploy

### Full Build (GitHub Actions)

```bash
vhal-gen deploy-test /path/to/flync-model \
    --vhal-dir /path/to/vhal-source \
    --sdk-dir /path/to/sdk-source \
    --aosp-tag android-14.0.0_r75
```

### Incremental Build (GCP Instance)

For iterative development with a pre-built AOSP tree on a GCP instance:

```bash
vhal-gen deploy-test /path/to/flync-model \
    --vhal-dir /path/to/vhal-source \
    --sdk-dir /path/to/sdk-source \
    --incremental \
    --gcp-instance aosp-builder \
    --gcp-zone us-central1-a
```

### Check GCP Instance Status

```bash
vhal-gen gcp-status --instance aosp-builder --zone us-central1-a
```

## Streamlit UI

A web-based UI provides a guided workflow through all stages:

```bash
source .venv/bin/activate
python -m streamlit run streamlit_app/app.py
```

The UI walks through:
1. Model inspection
2. Signal classification
3. VHAL source fetch from Gerrit
4. Code generation
5. Compile check
6. Deploy & test (GCP build + emulator push)

## Manual Emulator Deployment

After building on GCP or locally:

```bash
adb root && adb remount

# Push binaries
adb push $OUT/vendor/bin/hw/android.hardware.automotive.vehicle@V3-default-service \
    /vendor/bin/hw/android.hardware.automotive.vehicle@V1-emulator-service
adb push $OUT/vendor/bin/vehicle-daemon /vendor/bin/
adb push $OUT/vendor/etc/automotive/vhal/DefaultProperties.json \
    /vendor/etc/automotive/vhal/

# Set permissions
adb shell chmod 755 /vendor/bin/hw/android.hardware.automotive.vehicle@V1-emulator-service
adb shell chmod 755 /vendor/bin/vehicle-daemon

# Restart VHAL
adb shell stop vendor.vehicle-hal-emulator
adb shell start vendor.vehicle-hal-emulator

# Verify
adb shell getprop init.svc.vendor.vehicle-hal-emulator   # should be "running"
adb shell cmd car_service list-vhal-props                 # should list property IDs
```

## Project Structure

```
vhal-gen/
├── vhal_gen/
│   ├── cli.py                 # Click CLI entry point
│   ├── parser/                # FLYNC YAML model parser
│   ├── classifier/            # Signal → VehicleProperty mapper
│   ├── generator/             # Jinja2-based code generator
│   ├── builder/               # Local clang++ compile check
│   ├── fetcher/               # Gerrit VHAL source fetcher
│   ├── pipeline/              # Deploy orchestrator & GCP builder
│   ├── stubs/                 # AOSP header stubs for compile check
│   ├── templates/             # 12 Jinja2 code templates
│   └── models/                # Data model classes
├── streamlit_app/
│   └── app.py                 # Streamlit web UI
├── tests/                     # 67 pytest tests
└── pyproject.toml
```

## Running Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -q
```

## Dependencies

- Python 3.10+
- PyYAML >= 6.0
- Jinja2 >= 3.1
- Click >= 8.1
- Streamlit >= 1.28
- clang++ (for compile-check)
- gcloud CLI (for GCP build/deploy)
- adb (for emulator deployment)
