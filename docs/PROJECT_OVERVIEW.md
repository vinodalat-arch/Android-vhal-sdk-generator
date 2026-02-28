# vhal-gen: FLYNC YAML → Android VHAL Code Generator

## Purpose

Vehicle ECU networks define signals (lights, doors, speed, etc.) via FLYNC YAML model
files. A reference SDK already generates code that runs on ECU nodes (HPC, ZC_FL, ZC_FR,
etc.). `vhal-gen` makes these signals accessible to Android app developers on an IVI node
running Android Automotive 14.

## What It Does

`vhal-gen` is a Python tool that reads FLYNC YAML model files, maps signals to Android
VehicleProperty IDs, and generates all C++ source and config files needed to integrate
vehicle signals into the Android VHAL (Vehicle Hardware Abstraction Layer).

## Inputs

```
flync-model-dev-2/flync-model-dev/
├── general/channels/channels.yaml        # CAN bus topology, message direction
├── general/channels/pdus/*.flync.yaml    # PDU/signal definitions
├── general/vsm_states.flync.yaml         # Vehicle global states
├── general/vsm_api.flync.yaml            # VSM API definitions
└── ecus/*/                               # ECU configurations
```

## Output

A single VHAL project directory containing all generated code:

```
output/vhal/
├── BridgeVehicleHardware.h/.cpp   # Generic bridge (replaces FakeVehicleHardware)
├── IpcProtocol.h                   # Bridge ↔ daemon message protocol
├── VendorProperties.h              # Vendor property ID constants
├── DefaultProperties.json          # Property configs loaded by VHAL at boot
├── FlyncDaemon.h/.cpp             # Signal pack/unpack + transport logic
├── UdpTransport.h/.cpp            # Live UDP transport to vehicle network
├── MockTransport.h/.cpp           # Mock transport for emulator testing
├── flync-daemon.rc                 # Android init service config
├── Android.bp                      # Build file (bridge lib + daemon binary)
└── test-apk/
    ├── VhalTestActivity.java       # Test APK verifying all properties
    └── AndroidManifest.xml
```

## Architecture: Bridge + Daemon

```
┌──────────────────────────────────────────────────────┐
│  Android Apps                                        │
│  CarPropertyManager.getIntProperty(DOOR_LOCK, ...)   │
└──────────────────────┬───────────────────────────────┘
                       │ Binder
┌──────────────────────▼───────────────────────────────┐
│  CarService (AOSP, untouched)                        │
│  Discovers properties dynamically via                │
│  IVehicle::getAllPropConfigs() at boot                │
└──────────────────────┬───────────────────────────────┘
                       │ AIDL
┌──────────────────────▼───────────────────────────────┐
│  VHAL Process                                        │
│  ┌────────────────────────────────────────────────┐  │
│  │ DefaultVehicleHal (AOSP, untouched)            │  │
│  └──────────────┬─────────────────────────────────┘  │
│  ┌──────────────▼─────────────────────────────────┐  │
│  │ BridgeVehicleHardware (GENERATED, generic)     │  │
│  │  - Loads DefaultProperties.json at startup     │  │
│  │  - Unix Domain Socket server                   │  │
│  │  - Forwards get/set between VHAL ↔ daemon      │  │
│  │  - Fires onPropertyChangeEvent() on RX updates │  │
│  │  - ~200 lines C++, no signal-specific logic    │  │
│  └──────────────┬─────────────────────────────────┘  │
└─────────────────┼────────────────────────────────────┘
                  │ Unix Domain Socket
┌─────────────────▼────────────────────────────────────┐
│  flync-daemon (GENERATED, standalone native binary)  │
│  Built as part of same VHAL project (Android.bp)     │
│  Started via init.rc (flync-daemon.rc)               │
│  - Signal unpack (RX PDUs → property values)         │
│  - Signal pack (property set requests → TX PDUs)     │
│  - PropertyID ↔ signal mapping table                 │
│  - UDP socket to vehicle network (FDN Router)        │
│  - Pushes RX values to bridge via socket             │
│  - Receives TX set-requests from bridge via socket   │
│  - Configurable: mock mode or live UDP               │
└──────────────────┬───────────────────────────────────┘
                   │ UDP (Ethernet, VLAN 11)
                   ▼
            Vehicle ECUs (via HPC FDN Router)
```

## Key Design Decisions

### 1. Single VHAL Project Build — No Manifest Changes
The daemon is built as a `cc_binary` target within the same `Android.bp` as the
BridgeVehicleHardware `cc_library`. This means:
- **No `device.mk` / `product.mk` changes** — the daemon binary is declared in the
  VHAL project's own `Android.bp`, so it gets built and installed automatically when
  the VHAL module is built.
- **No AndroidManifest changes** — the daemon is a native binary, not an APK.
- **`init_rc` auto-registration** — `flync-daemon.rc` is referenced via the `init_rc`
  property in `Android.bp`. The build system packages it into `/vendor/etc/init/`, and
  Android's init process picks it up automatically at boot.
- **Single `mm`/`mma` build** — both the bridge library and daemon binary are built
  together in one module build.

### 2. No CarService or Framework Changes Required
CarService discovers properties dynamically at runtime — it has no hardcoded property
list. The discovery flow:
1. VHAL boots → `BridgeVehicleHardware` loads `DefaultProperties.json`
2. CarService boots → calls `IVehicle::getAllPropConfigs()` via AIDL
3. `DefaultVehicleHal` delegates to `BridgeVehicleHardware::getAllPropertyConfigs()`
4. CarService receives the full list (standard + vendor) and caches it
5. Apps use `CarPropertyManager` with any property ID — standard or vendor

**When signals change** (YAML model updated):
- Regenerate `DefaultProperties.json` + daemon code with `vhal-gen`
- Rebuild VHAL module with `mm` (partial build, ~2 min)
- No CarService rebuild, no framework rebuild, no full AOSP rebuild

### 3. Bridge is Generic, Daemon is Signal-Specific
This is the core architectural split:

| Component | Changes when... | Typical size |
|-----------|----------------|-------------|
| BridgeVehicleHardware | Android AIDL version changes (rare) | ~200 lines C++ |
| FlyncDaemon | YAML signal model changes (frequent) | ~500 lines C++ |
| DefaultProperties.json | YAML signal model changes (frequent) | ~200 lines JSON |

- **BridgeVehicleHardware** is a generic socket server that forwards IPC messages. It
  has zero knowledge of specific signals, PDUs, or bit layouts. It never needs
  regeneration when signals change.
- **FlyncDaemon** contains the generated signal table (property ID ↔ PDU bit position
  mappings) and pack/unpack logic. Regenerate whenever the YAML model changes.
- **Android version upgrades** only affect the bridge (if the `IVehicleHardware` AIDL
  interface changes). The daemon is Android-version-independent.

### 4. Daemon as Separate Process (Not In-Process)
The daemon runs as its own native process (`/vendor/bin/flync-daemon`) rather than
being linked directly into the VHAL process. Reasons:
- **Restartable independently** — if the daemon crashes or needs updating, VHAL stays
  running. `init` will restart the daemon automatically.
- **Reusable** — other services beyond VHAL can connect to the daemon's socket to
  access vehicle signals (e.g., a diagnostics service, a logging service).
- **Isolation** — signal pack/unpack bugs don't crash the VHAL process.
- **Testability** — the daemon can be tested standalone with the mock transport
  without needing a running VHAL.

### 5. IPC Protocol: Unix Domain Socket with Simple Framing
Bridge and daemon communicate via a Unix domain socket at `/dev/socket/flync-bridge`:
```
Message: [msg_type:4B][property_id:4B][area_id:4B][value_type:4B][value_len:4B][value:NB]
```
- **Why not Binder/AIDL?** Binder requires AIDL interface definition, code generation,
  and SELinux policy. A raw socket is simpler, has no framework dependencies, and the
  daemon can be built with minimal libraries.
- **Why not shared memory?** The message rate is low (signal updates at ~10-100 Hz).
  Socket overhead is negligible, and the request/response pattern maps naturally.

### 6. Deterministic Signal Classification — No AI/ML
Signal-to-property mapping uses a strict priority chain:
1. **Exact match table** — 14 signals map to known AOSP `VehicleProperty` IDs
   (e.g., `u8_TurnLight_req` → `TURN_SIGNAL_STATE`)
2. **Vendor fallback** — all remaining signals get auto-generated vendor property IDs
   using `VehiclePropertyGroup.VENDOR | VehicleArea.GLOBAL | type | counter`

No fuzzy matching, no keyword heuristics, no ML. Every run produces identical output
for the same input. The mapping table is human-auditable in `mapping_rules.py`.

### 7. No Full AOSP Build Required
The generated code integrates into an existing AOSP source tree at:
```
hardware/interfaces/automotive/vehicle/aidl/default/
```
Build with:
```bash
cd $AOSP_ROOT
source build/envsetup.sh
lunch <target>
cd hardware/interfaces/automotive/vehicle/aidl/default
mm    # builds just this module (~2 min)
```
Full AOSP build requires ~300+ GB disk space. This approach needs only the AOSP tree
to be synced — actual build is module-scoped.

### 8. Transport Abstraction — Mock vs Live
The daemon uses an `ITransport` interface with two implementations:
- **MockTransport** — generates cycling test values for all RX signals every 1 second.
  Used for emulator testing without vehicle hardware.
- **UdpTransport** — sends/receives PDUs over UDP to the vehicle network (VLAN 11,
  via HPC FDN Router). Used on real hardware.

Selected at daemon startup via `--mock` or `--udp` flag in `flync-daemon.rc`.

### 9. Start Bit Computation from YAML (Not Hardcoded)
FLYNC YAML PDU files specify signal `bit_length` but NOT `start_bit`. The parser
computes start bits by sequential accumulation:
```
signal[0].start_bit = 0
signal[i].start_bit = signal[i-1].start_bit + signal[i-1].bit_length
```
This matches the reference implementation in `ComConfig.cpp` and has been validated
against all 15 RX signals and 20 TX signals with 100% bit-position accuracy.

### 10. Vendor Property ID Allocation
Vendor IDs are deterministic and stable:
```
vendor_id = 0x20000000 (VENDOR) | 0x01000000 (GLOBAL) | type_bits | counter
```
- Counter starts at `0x0101` and increments per unique signal name
- Same signal name always gets the same ID (idempotent allocator)
- Boolean signals → `VehiclePropertyType.BOOLEAN` (0x00200000)
- Integer signals → `VehiclePropertyType.INT32` (0x00400000)
- Apps reference vendor IDs via constants from `VendorProperties.h`

### 11. Compile Check — Full Daemon Codebase Validation (Mandatory)
Before pushing generated code to a full AOSP build environment, `vhal-gen` provides a
local compile check using `clang++ -fsyntax-only` with minimal stub headers. **This check
MUST cover the entire daemon codebase** — not just the generated bridge files, but all
SDK reference code that the daemon depends on.

**Files that MUST be compiled (8 total):**

| # | File | Category |
|---|------|----------|
| 1 | `BridgeVehicleHardware.cpp` | Generated bridge |
| 2 | `FlyncDaemon.cpp` | Generated bridge |
| 3 | `Read_App_Signal_Data.cpp` | SDK reference (app/swc) |
| 4 | `Write_App_Signal_Data.cpp` | SDK reference (app/swc) |
| 5 | `iodata.cc` | SDK reference (can_io) |
| 6 | `ComConfig.cpp` | SDK reference (com) |
| 7 | `CanConfig.cpp` | SDK reference (com) |
| 8 | `com_utils.cpp` | SDK reference (com) |

**Stub headers** (in `vhal_gen/stubs/`) shadow real AOSP headers that only exist inside a
full build tree:
- `VehicleHalTypes.h` — all A14 AIDL types (StatusCode, VehiclePropValue, etc.)
- `android-base/logging.h` — no-op LOG macros
- `json/json.h` — minimal jsoncpp API surface

All stubs are derived from the exact Android 14 (`android-14.0.0_r1`) AIDL spec.

**macOS compatibility:** SDK's `iodata.cc` uses Linux `be32toh`/`htobe32`; on macOS these
are mapped to `OSSwapBigToHostInt32`/`OSSwapHostToBigInt32` via `-D` compile flags.

## How to Use

### CLI
```bash
vhal-gen generate ./flync-model-dev-2 -o ./output --transport mock
vhal-gen inspect ./flync-model-dev-2
vhal-gen classify ./flync-model-dev-2
vhal-gen compile-check --vhal-dir <path-to-vhal-tree> --sdk-dir <path-to-sdk-src>

# Full deploy-test pipeline (GitHub Actions build ~2 hours)
vhal-gen deploy-test ./flync-model-dev-2 --vhal-dir <path> --aosp-tag android-14.0.0_r75

# Incremental build on a GCP instance (~5-15 min)
vhal-gen deploy-test ./flync-model-dev-2 --vhal-dir <path> \
  --incremental --gcp-instance <instance-name> --gcp-zone us-central1-a

# Check GCP instance readiness
vhal-gen gcp-status --instance <instance-name> --zone us-central1-a
```

### Streamlit UI
```bash
streamlit run streamlit_app/app.py
```
The UI provides:
- **Architecture diagram** in Section 3 — interactive HTML/CSS layered diagram of the
  Android Automotive stack. Highlights which layers vhal-gen modifies (Bridge, Daemon,
  VehicleService, SDK) with color-coded tags (GENERATED, PATCHED, COPIED). Flow banner
  updates based on pipeline state
- **"Compile Check (Stubs)"** button in Section 4a — runs the full 8-file compile check
  and streams per-file PASS/FAIL results
- **GCP Instance Status card** in Section 4b — check instance readiness before building
- **Two build tabs** in Section 4b — "Full Build (GitHub Actions)" for complete AOSP
  builds, or "Incremental Build (GCP Instance)" for fast iterative development on a
  pre-existing instance with a completed AOSP build

### Integration
1. Copy `output/vhal/` contents into AOSP VHAL source directory
2. Build with `mm` or `mma`
3. Flash or push to device/emulator
4. Install test APK to verify

## Constraints
- Android 14 primary target (15/16 on roadmap)
- Python 3.10+ required
- Dependencies: pyyaml, jinja2, click, streamlit
