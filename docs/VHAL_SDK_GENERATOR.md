# VHAL SDK Generator — Comprehensive Documentation

> **Version:** 1.0.0 | **Target:** Android 14 (AIDL VHAL) | **Generator:** vhal-gen

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Why Android Automotive Compliance Matters](#2-why-android-automotive-compliance-matters)
3. [10 Key Features](#3-10-key-features)
4. [Architecture Overview](#4-architecture-overview)
5. [SDK Generation Method](#5-sdk-generation-method)
6. [Developer Workflow](#6-developer-workflow)
7. [YAML to VHAL Property Mapping](#7-yaml-to-vhal-property-mapping)
8. [Vendor Property Extension](#8-vendor-property-extension)
9. [Why the Daemon Approach Enables Portability](#9-why-the-daemon-approach-enables-portability)
10. [Android Automotive Compliance Analysis](#10-android-automotive-compliance-analysis)

---

## 1. Problem Statement

### The Gap Between Vehicle Networks and Android

Modern vehicles contain dozens of Electronic Control Units (ECUs) communicating
over CAN/CAN-FD/Ethernet buses. Each ECU exposes signals — headlight state,
door lock position, vehicle speed, ambient light level — packed into Protocol
Data Units (PDUs) at the bit level.

Android Automotive OS (AAOS) expects vehicle data through a completely different
interface: the **Vehicle Hardware Abstraction Layer (VHAL)**. VHAL speaks in
terms of `VehiclePropConfig`, `VehiclePropValue`, property IDs, area IDs, and
access modes defined by the AIDL `IVehicleHardware` interface.

**The problem is threefold:**

1. **Translation Complexity.** Every vehicle program requires hand-written C++
   code to unpack CAN signals from PDU buffers, map them to VHAL property IDs,
   handle type conversions, and manage the bidirectional flow between vehicle
   network and Android framework. This code is error-prone and takes weeks to
   develop per vehicle variant.

2. **Compliance Risk.** VHAL implementations must conform exactly to the AIDL
   interface contract — correct property types, access modes, area
   configurations, and callback patterns. A single deviation causes CTS/VTS
   test failures, blocking certification.

3. **Portability Burden.** OEMs support multiple Android versions across vehicle
   programs. Hand-written VHAL implementations embed version-specific
   assumptions (namespace paths, build system rules, init service formats) that
   break on upgrade.

### What vhal-gen Solves

`vhal-gen` eliminates manual VHAL integration entirely. Given a FLYNC YAML
model describing vehicle signals, it automatically:

- Parses PDU definitions and signal layouts
- Classifies each signal as a standard AOSP property or allocates a vendor ID
- Generates a complete, compilable VHAL bridge implementation
- Spawns a daemon that calls the Vehicle Body SDK's `get_*()`/`set_*()` functions
- Patches the stock AOSP VHAL source to use the generated bridge

The result: **zero hand-written C++** for the VHAL integration layer.

---

## 2. Why Android Automotive Compliance Matters

### Certification Requirements

Android Automotive devices must pass:

| Test Suite | What It Validates |
|---|---|
| **CTS** (Compatibility Test Suite) | CarService API behavior, property access patterns |
| **VTS** (Vendor Test Suite) | VHAL AIDL interface conformance, HAL health checks |
| **GAS** (Google Automotive Services) | Google Maps, Play Store, Assistant integration |

A non-compliant VHAL causes cascading failures: CarService cannot read
properties, apps like Google Maps lose vehicle speed data, and the device
fails certification.

### What Compliance Means in Practice

| Requirement | Consequence of Non-Compliance |
|---|---|
| Correct `IVehicleHardware` interface | VTS failure — HAL won't bind to framework |
| Standard property IDs (e.g., `0x0E010A01` for HEADLIGHTS_SWITCH) | CTS failure — CarService expects exact IDs |
| Proper access modes (READ vs READ_WRITE) | Security violation — writable properties exposed as read-only |
| AIDL enum types (not raw integers) | Compile failure against AIDL-generated headers |
| `VehiclePropConfig` with area configs | CarService property discovery fails |
| Async callback patterns for get/set | Framework deadlocks on synchronous calls |
| Vendor property IDs in `0x2XXXXXXX` range | Collision with standard property space |

### Why Generated Code Is Safer

Hand-written VHAL implementations commonly introduce:

- **Incorrect property ID encoding** — wrong group/area/type bit fields
- **Missing area configurations** — per-door properties registered as global
- **Stale vendor IDs** — collisions when new standard properties are added
- **Blocking calls** in async callbacks — causing ANR in CarService
- **Namespace errors** — using HIDL-era `V2_0` instead of AIDL namespaces

`vhal-gen` produces code from validated templates that are tested against the
Android 14 AIDL spec. Every generated file passes `clang++ -fsyntax-only`
with stub headers matching `android-14.0.0_r1`.

---

## 3. 10 Key Features

### 1. Automatic YAML-to-VHAL Property Mapping

Signals defined in FLYNC YAML are automatically classified as standard AOSP
properties (HEADLIGHTS_SWITCH, DOOR_LOCK, PERF_VEHICLE_SPEED, etc.) or
assigned unique vendor property IDs. No manual property ID assignment needed.

### 2. Full IVehicleHardware AIDL Implementation

Generates a complete `BridgeVehicleHardware` class implementing every method
of the Android 14 `IVehicleHardware` interface: `getAllPropertyConfigs()`,
`getValues()`, `setValues()`, `registerOnPropertyChangeEvent()`,
`checkHealth()`, and `dump()`.

### 3. Zero-Touch VHAL Patching

The generator modifies the stock AOSP source in-place:
- `VehicleService.cpp` — swaps `FakeVehicleHardware` → `BridgeVehicleHardware`
- `vhal/Android.bp` — updates static_libs, shared_libs, and required modules

No manual editing of AOSP source files required.

### 4. Vehicle Body SDK Integration

The generated daemon directly calls the SDK's `get_*()` and `set_*()` functions
(e.g., `get_u8_TurnLight_req()`, `set_bo_HazardLight_cmd()`). No custom bit
manipulation, PDU unpacking, or transport code needed — the SDK handles all
COM-layer concerns.

### 5. Child-Process Daemon Architecture

`BridgeVehicleHardware` spawns the daemon via `fork()+exec()` with
`socketpair()` IPC. This eliminates external dependencies:
- No `.rc` init service file
- No SELinux socket labels
- No modifications outside the VHAL module
- Automatic cleanup via `prctl(PR_SET_PDEATHSIG, SIGKILL)`

### 6. Crash-Resilient Watchdog

A watchdog thread monitors the daemon process via `waitpid()`. If the daemon
crashes, it is automatically respawned (up to 5 times) with a fresh
socketpair connection. The VHAL service continues running throughout.

### 7. AOSP-Format Property Configuration

Generates `DefaultProperties.json` in the exact format expected by the AOSP
VHAL framework (`{"apiVersion": 1, "properties": [...]}`), with correct
property IDs, access modes, change modes, area configs, and default values.

### 8. Compile-Check Without AOSP Source Tree

Built-in `compile-check` command runs `clang++ -fsyntax-only` against all
generated code using stub headers that match Android 14 AIDL types. Catches
compilation errors before the developer even touches the AOSP build system.

### 9. Deterministic Vendor ID Allocation

Vendor property IDs are allocated using a deterministic algorithm composing
`VehiclePropertyGroup.VENDOR | VehicleArea | VehiclePropertyType | counter`.
Same input YAML always produces same output IDs, enabling reproducible builds.

### 10. Per-Area Property Support

Signals like door locks are automatically mapped to per-area properties with
correct `VehicleAreaDoor` bitmasks (ROW_1_LEFT, ROW_1_RIGHT, ROW_2_LEFT,
ROW_2_RIGHT), matching AOSP CarService expectations for zoned properties.

---

## 4. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Android Framework                            │
│  CarService → CarPropertyManager → VehicleProperty APIs         │
└──────────────────────────┬──────────────────────────────────────┘
                           │ AIDL IVehicle
┌──────────────────────────┴──────────────────────────────────────┐
│  DefaultVehicleHal                                              │
│  (stock AOSP — unchanged)                                       │
└──────────────────────────┬──────────────────────────────────────┘
                           │ IVehicleHardware interface
┌──────────────────────────┴──────────────────────────────────────┐
│  BridgeVehicleHardware (GENERATED)                              │
│  - Implements IVehicleHardware                                  │
│  - Loads DefaultProperties.json                                 │
│  - Spawns FlyncDaemon as child process                          │
│  - Communicates over socketpair                                 │
│  - Watchdog thread for crash recovery                           │
└──────────────────────────┬──────────────────────────────────────┘
                           │ socketpair IPC (IpcMessage binary)
┌──────────────────────────┴──────────────────────────────────────┐
│  FlyncDaemon (GENERATED, child process)                         │
│  - Reads bridge FD from STDIN (inherited via dup2)              │
│  - Polls SDK get_*() for RX signals at ~50 Hz                  │
│  - Calls SDK set_*() for TX signals                             │
│  - Sends PROPERTY_CHANGED on value change                       │
│  - Handles GET_PROPERTY / SET_PROPERTY from bridge              │
└──────────────────────────┬──────────────────────────────────────┘
                           │ SDK function calls
┌──────────────────────────┴──────────────────────────────────────┐
│  Vehicle Body SDK (copied verbatim)                             │
│  app/swc/  → Read_App_Signal_Data.h  (get_*() RX getters)      │
│              Write_App_Signal_Data.h  (set_*() TX setters)      │
│  com/      → ComConfig, CanConfig, com_utils (PDU pack/unpack) │
│  can_io/   → iodata (wire format serialization)                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │ UDP / CAN-FD
                    Vehicle Network Bus
```

### IPC Protocol

Communication between Bridge and Daemon uses a compact binary protocol:

```c
struct __attribute__((packed)) IpcMessage {
    IpcMsgType   msg_type;     // SET_PROPERTY, GET_PROPERTY, PROPERTY_CHANGED, PROPERTY_RESPONSE
    int32_t      property_id;  // VHAL property ID
    int32_t      area_id;      // Area bitmask
    IpcValueType value_type;   // BOOLEAN, INT32, FLOAT, INT64
    uint32_t     value_len;    // Payload size in bytes
    uint8_t      value[];      // Flexible array member
};
```

### Process Lifecycle

```
VehicleService boots
  → DefaultVehicleHal created
  → BridgeVehicleHardware constructor:
      1. loadPropertyConfigs("DefaultProperties.json")
      2. spawnDaemon():
         a. socketpair(AF_UNIX, SOCK_STREAM, 0, fds)
         b. fork()
         c. Child: prctl(PR_SET_PDEATHSIG, SIGKILL)
                   dup2(fds[1], STDIN_FILENO)
                   execl("/vendor/bin/flync-daemon")
         d. Parent: mClientFd = fds[0]
      3. Start rxThreadLoop (reads PROPERTY_CHANGED from daemon)
      4. Start watchdogLoop (waitpid → respawn on crash)
```

---

## 5. SDK Generation Method

### Input

| Input | Description |
|---|---|
| FLYNC YAML model directory | PDU definitions, channel configs, global states |
| VHAL source tree | Pulled from Android Gerrit (`automotive/vehicle/aidl/`) |
| Vehicle Body SDK (optional) | Reference `get_*()`/`set_*()` source files |

### Generation Pipeline

```
YAML Files ──→ Parser ──→ FlyncModel ──→ Classifier ──→ PropertyMappings ──→ Generator ──→ C++ / JSON / BP
```

**Stage 1: Parse** (`model_loader.py`)
- Load all `*.flync.yaml` PDU files → `PDU` objects with `Signal` lists
- Parse `channels.yaml` → determine RX/TX direction per PDU
- Parse `vsm_states.flync.yaml` → global vehicle states
- Output: `FlyncModel` with fully resolved directions

**Stage 2: Classify** (`signal_classifier.py`)
- For each signal in each PDU:
  - Check `EXACT_MATCH_RULES` → standard AOSP property
  - Fallback → allocate vendor property ID via `VendorIdAllocator`
  - Derive SDK function names from signal name prefix
  - Skip housekeeping signals (`crc16`, `counter`)
- Output: `list[PropertyMapping]`

**Stage 3: Generate** (`generator_engine.py`)
- Render 11 Jinja2 templates into `impl/bridge/`
- Copy 12 SDK source files into `impl/bridge/sdk/`
- Patch `VehicleService.cpp` in-place (Fake → Bridge)
- Modify `vhal/Android.bp` cc_binary block
- Output: 23 files + 2 patched stock files

### Generated File Manifest

| File | Purpose |
|---|---|
| `BridgeVehicleHardware.h` | IVehicleHardware implementation header |
| `BridgeVehicleHardware.cpp` | Bridge logic: config loading, socketpair, IPC |
| `FlyncDaemon.h` | Daemon class with signal bindings |
| `FlyncDaemon.cpp` | Signal table, SDK dispatchers, main() |
| `IpcProtocol.h` | Binary IPC message definitions |
| `VendorProperties.h` | Vendor property ID constants |
| `DefaultProperties.json` | AOSP-format property configurations |
| `Android.bp` | Build rules for bridge library and daemon binary |
| `INTEGRATION.md` | Deployment guide |
| `test-apk/VhalTestActivity.java` | Android test app for property verification |
| `test-apk/AndroidManifest.xml` | Test app manifest |
| `sdk/` (12 files) | Vehicle Body SDK source (copied verbatim) |

---

## 6. Developer Workflow

### Prerequisites

- macOS or Linux development machine
- Python 3.14+ with the `vhal-gen` package installed
- `clang++` for compile-check (Xcode on macOS)
- FLYNC YAML model for the target vehicle
- Vehicle Body SDK source (`performance-stack-*/src/`)

### Step-by-Step

#### Step 1: Pull VHAL Source from Gerrit

```bash
# Via Streamlit UI (recommended):
# Click "Pull VHAL Source" button, select tag android-14.0.0_r75

# Or via Python API:
python -c "
from vhal_gen.fetcher.gerrit_fetcher import GerritFetcher
fetcher = GerritFetcher()
for line in fetcher.fetch_vhal(Path('output'), tag='android-14.0.0_r75'):
    print(line)
"
```

This performs a sparse checkout of `automotive/vehicle/aidl/` (264 files,
~2.3 MB) from Android Gerrit. The full VHAL tree is pulled — all
implementation files, build configs, tests, and AIDL definitions.

#### Step 2: Generate Bridge Code

```bash
vhal-gen generate ./flync-model-dev-2 \
  --vhal-dir ./output/aosp-vhal/android-14.0.0_r75/automotive/vehicle/aidl \
  --sdk-dir ./performance-stack-Body-lighting-Draft/src
```

Output:
```
Loading FLYNC model from: ./flync-model-dev-2
  Parsed 10 PDUs, 49 signals
Classifying signals...
  14 standard AOSP mappings, 29 vendor mappings
Generating code into VHAL tree...
  Generated 23 files to impl/bridge/
Done — VehicleService.cpp and vhal/Android.bp auto-modified.
```

#### Step 3: Compile Check (Local Verification)

```bash
vhal-gen compile-check \
  --vhal-dir ./output/aosp-vhal/android-14.0.0_r75/automotive/vehicle/aidl
```

Output:
```
Found 8 source file(s) under bridge/
  PASS BridgeVehicleHardware.cpp
  PASS FlyncDaemon.cpp
  PASS sdk/app/swc/Read_App_Signal_Data.cpp
  PASS sdk/app/swc/Write_App_Signal_Data.cpp
  PASS sdk/can_io/src/iodata.cc
  PASS sdk/com/src/CanConfig.cpp
  PASS sdk/com/src/ComConfig.cpp
  PASS sdk/com/src/com_utils.cpp
All 8 file(s) passed compile check.
```

#### Step 4: Review Changes

```bash
cd output/aosp-vhal/android-14.0.0_r75
git status
```

```
 M automotive/vehicle/aidl/impl/vhal/Android.bp          # 2 lines changed
 M automotive/vehicle/aidl/impl/vhal/src/VehicleService.cpp  # 3 lines changed
?? automotive/vehicle/aidl/impl/bridge/                   # 23 new files
```

Only **2 stock files modified** (minimal, surgical changes). All new code is
self-contained in `impl/bridge/`.

#### Step 5: Commit and Build

```bash
git checkout -b flync-bridge
git add -A
git commit -m "Add FLYNC bridge: BridgeVehicleHardware + daemon"

# Build in AOSP environment
cd $AOSP_ROOT
source build/envsetup.sh
lunch <automotive-target>
cd hardware/interfaces/automotive/vehicle/aidl/impl
mma
```

#### Step 6: Deploy and Verify

```bash
adb root && adb remount
adb push $OUT/vendor/bin/hw/android.hardware.automotive.vehicle@V*-default-service \
         /vendor/bin/hw/
adb push $OUT/vendor/bin/flync-daemon /vendor/bin/
adb push $OUT/vendor/etc/automotive/vhal/DefaultProperties.json \
         /vendor/etc/automotive/vhal/
adb shell setenforce 0

# Restart VHAL (daemon auto-spawns as child process)
adb shell stop vendor.vehicle.hal.default
adb shell start vendor.vehicle.hal.default

# Verify
adb logcat -s BridgeVHAL:* FlyncDaemon:*
```

#### Alternative: Automated Deploy-Test Pipeline

The `deploy-test` command automates Steps 5–6 end-to-end:

```bash
# Full build via GitHub Actions (~2 hours)
vhal-gen deploy-test ./flync-model-dev-2 \
  --vhal-dir ./output/aosp-vhal/android-14.0.0_r75/automotive/vehicle/aidl \
  --aosp-tag android-14.0.0_r75 --git-ref main
```

For iterative development on a GCP instance that already has a completed AOSP
build, use the incremental mode (~5–15 min):

```bash
# Check instance status first
vhal-gen gcp-status --instance aosp-builder-1 --zone us-central1-a

# Incremental build: sync code → mma → pull artifacts → deploy → verify
vhal-gen deploy-test ./flync-model-dev-2 \
  --vhal-dir ./output/aosp-vhal/android-14.0.0_r75/automotive/vehicle/aidl \
  --incremental --gcp-instance aosp-builder-1 --gcp-zone us-central1-a
```

The incremental pipeline:
1. Verifies gcloud CLI and instance status
2. SCPs generated bridge code to `~/aosp/.../impl/bridge/` on the instance
3. Runs `mma -j$(nproc)` via SSH for an incremental build
4. Pulls 3 artifacts (VHAL service, daemon, config JSON) back locally
5. Deploys to emulator and verifies properties

The Streamlit UI (Section 4b) also provides both modes with a GCP Instance
Status card that shows whether the instance is ready for incremental builds.

The UI also features an **interactive architecture diagram** (Section 3) showing the
full Android Automotive layer stack with highlighted layers indicating what vhal-gen
modifies. Tags (GENERATED, PATCHED, COPIED) and a flow banner update based on the
current pipeline state.

---

## 7. YAML to VHAL Property Mapping

### Input: FLYNC YAML Signal Definition

```yaml
# ExteriorLighting_Doors_Req.flync.yaml
name: ExteriorLighting_Doors_Req
id: 0x401
length: 8
signals:
  - signal:
      name: u8_TurnLight_req
      bit_length: 3
      base_data_type: uint8
  - signal:
      name: bo_Crash_Detection_sts
      bit_length: 1
      base_data_type: bool
  - signal:
      name: u8_VehSpd_kmph
      bit_length: 8
      base_data_type: uint8
      lower_limit: 0
      upper_limit: 240
```

### Classification Pipeline

```
Signal Name ──→ Exact Match? ──yes──→ Standard AOSP Property
                    │ no
                    └──→ Vendor ID Allocation
```

#### Stage 1: Exact Match Rules

The classifier maintains a curated rule table mapping known signal names to
standard AOSP VehicleProperty IDs:

| Signal Name | AOSP Property | Property ID | Access |
|---|---|---|---|
| `u8_MainLightSelector_Req` | HEADLIGHTS_SWITCH | `0x0E010A01` | READ |
| `u8_Beam_Req` | HIGH_BEAM_LIGHTS_SWITCH | `0x0E010A03` | READ |
| `u8_TurnLight_req` | TURN_SIGNAL_STATE | `0x0E010A04` | READ |
| `u8_HazardLight_req` | HAZARD_LIGHTS_STATE | `0x0E010A05` | READ |
| `u8_VehSpd_kmph` | PERF_VEHICLE_SPEED | `0x11600207` | READ |
| `bo_DoorLock_Sw` | DOOR_LOCK (global) | `0x0B010B00` | READ |
| `bo_FL_Unlock_Sts` | DOOR_LOCK (front-left) | `0x0B010B00` | READ |
| `bo_FR_Unlock_Sts` | DOOR_LOCK (front-right) | `0x0B010B00` | READ |
| `u8_ALS_Data` | NIGHT_MODE | `0x11200407` | READ |

Each rule specifies the full property configuration: area type, property type,
access mode, change mode, and optional unit conversion flags.

#### Stage 2: Vendor Fallback

Signals not matching any rule receive a vendor property ID:

```
vendor_id = 0x20000000        ← VehiclePropertyGroup.VENDOR
          | 0x01000000        ← VehicleArea.GLOBAL
          | type_bits         ← BOOLEAN=0x00200000, INT32=0x00400000, FLOAT=0x00600000
          | counter           ← Sequential from 0x0101
```

Access is inferred from PDU direction:
- **RX PDU** (vehicle → IVI): `VehiclePropertyAccess.READ`
- **TX PDU** (IVI → vehicle): `VehiclePropertyAccess.READ_WRITE`

#### Stage 3: SDK Function Binding

Signal names with type prefixes (`bo_`, `u8_`, `u16_`, etc.) automatically
bind to SDK functions:

| Direction | Signal | SDK Function |
|---|---|---|
| RX | `u8_TurnLight_req` | `get_u8_TurnLight_req()` |
| RX | `bo_Crash_Detection_sts` | `get_bo_Crash_Detection_sts()` |
| TX | `bo_HazardLight_cmd` | `set_bo_HazardLight_cmd()` |
| TX | `bo_DRL_cmd` | `set_bo_DRL_cmd()` |

These bindings are emitted into the daemon's generated signal table and switch
dispatchers.

### Output: Generated Artifacts

**DefaultProperties.json** (AOSP format):
```json
{
    "apiVersion": 1,
    "properties": [
        {
            "property": "VehicleProperty::TURN_SIGNAL_STATE",
            "propertyId": 235340292,
            "defaultValue": {"int32Values": [0]},
            "areas": [{"areaId": 0, "minInt32Value": 0, "maxInt32Value": 7}],
            "access": "VehiclePropertyAccess::READ",
            "changeMode": "VehiclePropertyChangeMode::ON_CHANGE"
        }
    ]
}
```

**FlyncDaemon.cpp** (signal table):
```cpp
const SignalBinding kSignalTable[] = {
    {
        .property_id = static_cast<int32_t>(0x0E010A04),
        .area_id     = 0,
        .is_rx       = true,
        .signal_name = "u8_TurnLight_req",
        .value_type  = IpcValueType::INT32,
    },
    // ... 39 more entries
};
```

**FlyncDaemon.cpp** (SDK dispatcher):
```cpp
int32_t pollRxSignal(size_t idx) {
    switch (idx) {
        case 0: return static_cast<int32_t>(get_u8_TurnLight_req());
        case 1: return static_cast<int32_t>(get_bo_Crash_Detection_sts());
        // ...
    }
    return 0;
}
```

---

## 8. Vendor Property Extension

### Why Vendor Properties Are Needed

The AOSP VHAL defines ~200 standard properties (lights, doors, HVAC, etc.).
Vehicle-specific signals that don't map to any standard property — such as
proprietary light modes, custom sensor data, or OEM-specific controls — must
use the **vendor property extension mechanism**.

### Vendor ID Structure

Android reserves the `0x2XXXXXXX` range for vendor properties. `vhal-gen`
allocates IDs by composing four fields:

```
Bits 31-28:  0x2 ─── VehiclePropertyGroup.VENDOR
Bits 27-24:  0x1 ─── VehicleArea.GLOBAL (default)
Bits 23-20:  type ── 0x2=BOOLEAN, 0x4=INT32, 0x6=FLOAT
Bits 19-0:   counter ── Sequential from 0x00101
```

### Allocation Algorithm

```python
class VendorIdAllocator:
    def allocate(self, signal_name, base_data_type):
        # 1. Return cached ID if signal already allocated
        if signal_name in self._cache:
            return self._cache[signal_name]

        # 2. Map data type to VHAL property type
        type_bits = {
            "bool":    0x00200000,  # BOOLEAN
            "uint8":   0x00400000,  # INT32
            "uint16":  0x00400000,  # INT32
            "float32": 0x00600000,  # FLOAT
        }[base_data_type]

        # 3. Compose vendor ID
        vendor_id = 0x20000000 | 0x01000000 | type_bits | self._counter

        # 4. Increment counter, cache, and return
        self._counter += 1
        self._cache[signal_name] = vendor_id
        return vendor_id
```

### Generated Output

**VendorProperties.h:**
```cpp
#pragma once
#include <cstdint>

namespace vendor::properties {

constexpr int32_t VENDOR_BO_DRL_CMD = 0x21200101;
constexpr int32_t VENDOR_BO_FRONTRIGHT_LIGHT_CMD = 0x21200102;
constexpr int32_t VENDOR_U8_BLINKFREQ_REQ = 0x21400103;
// ... 29 vendor properties total

}  // namespace vendor::properties
```

### Determinism Guarantee

The allocator uses a fixed starting counter (`0x0101`) and processes signals
in YAML file order. This means:

- **Same YAML → same vendor IDs** across regeneration
- **Reproducible builds** — no random ID assignment
- **Stable API** — Android apps referencing vendor IDs won't break on regen

### Consumer-Side Usage

Android apps access vendor properties through the standard CarPropertyManager:

```java
CarPropertyManager pm = car.getCarManager(CarPropertyManager.class);

// Read a vendor property
int drlState = pm.getIntProperty(0x21200101, 0);  // VENDOR_BO_DRL_CMD

// Write a vendor property (if READ_WRITE)
pm.setIntProperty(0x21200102, 0, 1);  // VENDOR_BO_FRONTRIGHT_LIGHT_CMD = ON
```

---

## 9. Why the Daemon Approach Enables Portability

### The Portability Problem

VHAL implementations are tightly coupled to the Android version they target:

| Coupling Point | Android 13 | Android 14 | Android 15+ |
|---|---|---|---|
| VHAL interface | HIDL `IVehicle 2.0` | AIDL `IVehicleHardware` | AIDL (may evolve) |
| Build system | `Android.mk` or `.bp` | `Android.bp` with AIDL libs | Same or evolved |
| Init system | `.rc` service files | `.rc` service files | `.rc` or new format |
| SELinux policy | Version-specific contexts | Version-specific contexts | New contexts |
| Namespace | `V2_0::impl` | `vehicle::bridge` | May change |

A monolithic VHAL implementation that handles everything (signal translation,
network I/O, property management) in one binary must be rewritten for each
Android version.

### How the Daemon Architecture Solves This

The generated code uses a **two-process split**:

```
┌────────────────────────────────┐   ┌──────────────────────────────┐
│  BridgeVehicleHardware         │   │  FlyncDaemon                 │
│  (VHAL-version-specific)       │   │  (Android-version-agnostic)  │
│                                │   │                              │
│  • IVehicleHardware impl       │   │  • SDK get_*()/set_*() calls │
│  • AIDL types and callbacks    │   │  • Signal polling loop       │
│  • Property config loading     │   │  • IPC message handling      │
│  • Spawns daemon via fork()    │   │  • Reads FD from STDIN       │
│                                │   │  • No AIDL dependencies      │
└───────────────┬────────────────┘   └──────────────┬───────────────┘
                │         socketpair IPC             │
                └────────────────────────────────────┘
```

**The daemon has zero AIDL dependencies.** It links only against:
- `libbase` (Android logging)
- `liblog`
- `libutils`
- Vehicle Body SDK (static, copied into build)

This means the daemon binary **compiles unchanged across Android versions**.
Only `BridgeVehicleHardware` needs to match the target VHAL interface.

### What Changes Per Android Version

| Component | Needs Update? | Effort |
|---|---|---|
| FlyncDaemon binary | **No** | Zero |
| Vehicle Body SDK | **No** | Zero |
| IPC protocol | **No** | Zero |
| Signal table | **No** | Zero |
| BridgeVehicleHardware | **Yes** — template | Update template, regenerate |
| Android.bp | **Yes** — template | Update template, regenerate |
| VehicleService.cpp patch | **Yes** — template | Update patch pattern |

When Android 15 ships with a modified `IVehicleHardware` interface, the
fix is:

1. Update `BridgeVehicleHardware.h.j2` and `.cpp.j2` templates
2. Regenerate

The daemon, SDK, signal table, and IPC protocol remain untouched.

### Why Not a Single Process?

A single-process approach (embedding SDK calls directly in
BridgeVehicleHardware) would:

1. **Force SDK recompilation** against AIDL headers on each Android version
2. **Couple SDK build rules** to VHAL build system changes
3. **Risk SDK symbol conflicts** with VHAL framework libraries
4. **Prevent independent testing** of the signal translation layer

The two-process split with socketpair provides clean isolation while adding
negligible overhead (IPC messages are ~20 bytes, sent at signal change rate).

### The `init_rc` Elimination

Previous approaches required an `.rc` file to start the daemon:

```
# OLD: Required init_rc, SELinux labels, vendor partition changes
service flync-daemon /vendor/bin/flync-daemon
    class hal
    user vehicle_network
    group vehicle_network
```

The child-process approach eliminates this entirely:

```cpp
// NEW: Daemon spawned by BridgeVehicleHardware constructor
void BridgeVehicleHardware::spawnDaemon() {
    socketpair(AF_UNIX, SOCK_STREAM, 0, fds);
    pid_t pid = fork();
    if (pid == 0) {
        prctl(PR_SET_PDEATHSIG, SIGKILL);
        dup2(fds[1], STDIN_FILENO);
        execl("/vendor/bin/flync-daemon", ...);
    }
    mClientFd = fds[0];
}
```

Benefits:
- **No SELinux socket labels** — socketpair is anonymous
- **No init coordination** — daemon lifecycle tied to VHAL process
- **No vendor partition changes** beyond the VHAL module itself
- **Automatic cleanup** — `PR_SET_PDEATHSIG` kills daemon if VHAL dies

---

## 10. Android Automotive Compliance Analysis

### AIDL Interface Conformance

The generated `BridgeVehicleHardware` implements every method of the
`IVehicleHardware` interface defined in AOSP:

| Interface Method | Implementation | Compliance |
|---|---|---|
| `getAllPropertyConfigs()` | Returns configs loaded from DefaultProperties.json | Correct config format with areas |
| `getValues()` | Async callback with local cache + IPC fallback | Non-blocking, callback-based |
| `setValues()` | Async callback, forwards SET_PROPERTY via IPC | Non-blocking, callback-based |
| `registerOnPropertyChangeEvent()` | Stores callback, invoked from RX thread | Push-based notification |
| `registerOnPropertySetErrorEvent()` | Stores callback | Error propagation ready |
| `checkHealth()` | Returns OK if daemon connected and running | HAL health monitoring |
| `dump()` | Reports config count, connection status, cache size | Diagnostic support |
| `updateSampleRate()` | Returns OK (daemon polls at native rate) | Rate control interface |

### Property ID Compliance

| Property Type | ID Range | Encoding | Status |
|---|---|---|---|
| Standard (lights, doors, speed) | `0x0XXXXXXX` | AOSP-defined exact IDs | Matches `VehicleProperty.aidl` |
| Vendor (OEM-specific signals) | `0x2XXXXXXX` | GROUP.VENDOR + area + type + counter | Correct vendor range |

### AIDL Type Usage

The generated code uses AIDL enum types throughout — never raw integers:

```cpp
// CORRECT (generated):
config.access = VehiclePropertyAccess::READ_WRITE;
config.changeMode = VehiclePropertyChangeMode::ON_CHANGE;
result.status = StatusCode::OK;

// WRONG (hand-written code often does this):
config.access = 3;  // Magic number
```

### Build System Compliance

The generated `Android.bp` follows AOSP conventions:

- `cc_library` for BridgeVehicleHardware (linked into VHAL service)
- `cc_binary` for flync-daemon (separate executable)
- `prebuilt_etc` for DefaultProperties.json (installed to `/vendor/etc/`)
- `VehicleHalDefaults` defaults module (inherits standard VHAL build config)
- No hardcoded AIDL version numbers (`@V1`, `@V3`)

### Namespace Compliance

```cpp
// Generated namespace (AIDL-era, Android 14):
namespace android::hardware::automotive::vehicle::bridge { ... }

// NOT the HIDL-era namespace:
namespace android::hardware::automotive::vehicle::V2_0::impl { ... }
```

### Property Configuration Compliance

DefaultProperties.json follows the exact AOSP format consumed by
`JsonConfigLoader`:

```json
{
    "apiVersion": 1,
    "properties": [{
        "property": "VehicleProperty::HEADLIGHTS_SWITCH",
        "propertyId": 235340289,
        "defaultValue": {"int32Values": [0]},
        "areas": [{"areaId": 0}],
        "access": "VehiclePropertyAccess::READ",
        "changeMode": "VehiclePropertyChangeMode::ON_CHANGE"
    }]
}
```

### What Passes CTS/VTS

| Test Category | What's Tested | Generated Code Handles |
|---|---|---|
| Property enumeration | `getAllPropertyConfigs()` returns valid configs | DefaultProperties.json loaded at startup |
| Property read | `getValues()` returns correct types and status | Local cache + IPC to daemon |
| Property write | `setValues()` accepts valid values | IPC to daemon → SDK `set_*()` |
| Property subscription | `registerOnPropertyChangeEvent()` fires on change | RX thread pushes PROPERTY_CHANGED |
| HAL health | `checkHealth()` returns OK | Checks daemon connection and running state |
| Vendor properties | IDs in vendor range, correct encoding | Deterministic `0x2XXXXXXX` allocation |
| Area properties | Per-door/seat properties with correct area IDs | DOOR_LOCK mapped per-area with bitmasks |

### Summary: Compliance Checklist

- [x] Implements `IVehicleHardware` AIDL interface (Android 14)
- [x] Uses AIDL enum types (not raw integers)
- [x] Standard properties use exact AOSP property IDs
- [x] Vendor properties allocated in `0x2XXXXXXX` range
- [x] Property configs include area configurations
- [x] Async callback pattern for `getValues()`/`setValues()`
- [x] `DefaultProperties.json` in AOSP `apiVersion: 1` format
- [x] Build rules use `VehicleHalDefaults` and standard AOSP conventions
- [x] AIDL-era namespace (`vehicle::bridge`, not `V2_0::impl`)
- [x] No hardcoded AIDL version numbers in build files
- [x] No modifications outside VHAL module (no `.rc`, no SELinux changes)
- [x] Compile-verified against Android 14 AIDL stub headers
