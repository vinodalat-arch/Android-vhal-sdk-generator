# Android VHAL Architecture & Bridge+Daemon Design

## Android 14 AIDL VHAL Stack

```
┌─────────────────────────────────────────────────────┐
│  App Layer                                          │
│  CarPropertyManager.getIntProperty(propId, areaId)  │
│  CarPropertyManager.registerCallback(propId, cb)    │
└──────────────────────┬──────────────────────────────┘
                       │ Binder IPC
┌──────────────────────▼──────────────────────────────┐
│  CarService (system_server process)                 │
│  - CarPropertyService                               │
│  - Discovers properties via getAllPropConfigs()      │
│  - Routes get/set/subscribe to VHAL                 │
│  - NO CHANGES NEEDED for new properties             │
└──────────────────────┬──────────────────────────────┘
                       │ AIDL (android.hardware.automotive.vehicle)
┌──────────────────────▼──────────────────────────────┐
│  VHAL HAL Process                                   │
│  ┌───────────────────────────────────────────────┐  │
│  │ DefaultVehicleHal (AOSP stock)                │  │
│  │ - Implements IVehicle AIDL interface           │  │
│  │ - Calls IVehicleHardware for actual values     │  │
│  │ - Handles subscriptions/batching               │  │
│  └──────────────┬────────────────────────────────┘  │
│  ┌──────────────▼────────────────────────────────┐  │
│  │ IVehicleHardware (interface)                   │  │
│  │ - getAllPropertyConfigs()                       │  │
│  │ - getValues() / setValues()                    │  │
│  │ - registerOnPropertyChangeEvent()              │  │
│  └──────────────┬────────────────────────────────┘  │
│                 │                                    │
│  ┌──────────────▼────────────────────────────────┐  │
│  │ BridgeVehicleHardware (GENERATED)             │  │
│  │ Replaces: FakeVehicleHardware                  │  │
│  └───────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

## Property Discovery Flow (No Rebuild Needed for CarService)

```
1. VHAL boots
   → BridgeVehicleHardware::init()
   → Reads DefaultProperties.json
   → Populates in-memory property config map

2. CarService boots
   → Binds to IVehicle HAL
   → Calls getAllPropConfigs()
   → DefaultVehicleHal → BridgeVehicleHardware::getAllPropertyConfigs()
   → Returns all property configs (standard + vendor)
   → CarService caches them, ready to serve apps

3. App calls CarPropertyManager.getIntProperty(VENDOR_PROP_X, 0)
   → CarService → IVehicle::getValues()
   → DefaultVehicleHal → BridgeVehicleHardware::getValues()
   → Bridge sends GET_PROPERTY to daemon via socket
   → Daemon looks up current signal value
   → Returns value via socket
   → Bridge returns to VHAL → CarService → App
```

## BridgeVehicleHardware Design

### Responsibilities
- Load property configs from `DefaultProperties.json` at startup
- Implement `IVehicleHardware` interface (getAllPropertyConfigs, getValues, setValues)
- Run a Unix Domain Socket server for daemon communication
- Forward get/set requests to daemon
- Fire `onPropertyChangeEvent()` when daemon pushes updated values

### What it does NOT do
- No signal-specific logic
- No pack/unpack
- No transport layer
- No knowledge of PDU structure

### Socket Server
- Path: `/dev/socket/flync-bridge` (or abstract namespace `@flync-bridge`)
- Single-threaded event loop with epoll
- Accepts one connection from flync-daemon

---

## flync-daemon Design

### Responsibilities
- Connect to BridgeVehicleHardware via Unix Domain Socket
- Maintain signal→property mapping table
- RX path: receive UDP PDUs → unpack signals → push property updates to bridge
- TX path: receive set-property from bridge → pack into PDU → send via UDP
- Support mock transport (loopback/simulated values) for emulator

### Signal Table
Generated as a static C++ array:
```cpp
struct SignalEntry {
    int32_t property_id;
    int32_t area_id;
    uint16_t pdu_id;
    uint8_t start_bit;
    uint8_t bit_length;
    uint8_t bitmask;
    bool is_rx;
};

static const SignalEntry SIGNAL_TABLE[] = {
    // property_id,          area_id, pdu_id, start, len, mask, is_rx
    {HEADLIGHTS_SWITCH,      0,       0x401,  12,    2,   0x03, true},
    {TURN_SIGNAL_STATE,      0,       0x401,  0,     3,   0x07, true},
    // ...
};
```

---

## IPC Protocol (Bridge ↔ Daemon)

### Message Format
```
┌──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
│ msg_type │ prop_id  │ area_id  │ val_type │ val_len  │ value    │
│ 4 bytes  │ 4 bytes  │ 4 bytes  │ 4 bytes  │ 4 bytes  │ N bytes  │
└──────────┴──────────┴──────────┴──────────┴──────────┴──────────┘
```

### Message Types
| Type | Value | Direction | Description |
|------|-------|-----------|-------------|
| SET_PROPERTY | 1 | bridge→daemon | App wants to set a value |
| GET_PROPERTY | 2 | bridge→daemon | App wants to read a value |
| PROPERTY_CHANGED | 3 | daemon→bridge | Signal value updated from vehicle |
| PROPERTY_RESPONSE | 4 | daemon→bridge | Response to GET_PROPERTY |

### Value Types
| Type | Value | Size |
|------|-------|------|
| BOOLEAN | 1 | 4 bytes (int32, 0 or 1) |
| INT32 | 2 | 4 bytes |
| FLOAT | 3 | 4 bytes |
| INT64 | 4 | 8 bytes |

---

## Build Integration

### Single Android.bp with Three Targets

```blueprint
// Bridge library linked into VHAL service process
cc_library {
    name: "android.hardware.automotive.vehicle-bridge-hardware-lib",
    srcs: ["BridgeVehicleHardware.cpp"],
    defaults: ["VehicleHalDefaults"],
    header_libs: ["IVehicleHardware"],
    shared_libs: ["libbase", "liblog", "libutils", "libjsoncpp"],
}

// VHAL service binary (replaces stock FakeVehicleHardware service)
cc_binary {
    name: "android.hardware.automotive.vehicle@V1-bridge-service",
    srcs: ["VehicleService.cpp"],
    static_libs: ["...-bridge-hardware-lib", "DefaultVehicleHal", "VehicleHalUtils"],
    init_rc: ["vhal-bridge-service.rc"],
    vintf_fragments: ["vhal-bridge-service.xml"],
}

// Standalone daemon binary
cc_binary {
    name: "flync-daemon",
    srcs: ["FlyncDaemon.cpp", "UdpTransport.cpp", "MockTransport.cpp"],
    init_rc: ["flync-daemon.rc"],
}

// JSON config installed to /vendor/etc/automotive/vhal/
prebuilt_etc {
    name: "DefaultProperties.json",
    src: "DefaultProperties.json",
    sub_dir: "automotive/vhal",
    vendor: true,
}
```

### Build Commands
```bash
# From AOSP root, build just the VHAL module:
cd hardware/interfaces/automotive/vehicle/aidl/default
mm          # Build current module
mma         # Build current module and dependencies
```

### No Manifest Changes
- `flync-daemon.rc` uses `init_rc` property in Android.bp
- `vhal-bridge-service.rc` and `vhal-bridge-service.xml` register the VHAL service
- Android build system automatically includes them in the system image
- No need to modify `device.mk`, `product.mk`, or `AndroidManifest.xml`

---

## Compile Check — Full Daemon Codebase Validation (Mandatory)

Before pushing to AOSP, `vhal-gen` provides a local compile check using
`clang++ -fsyntax-only` with A14-compatible stub headers. **This MUST compile the
entire daemon codebase** — both generated and SDK reference code.

### Files Covered (8 total)

| File | Category | Description |
|------|----------|-------------|
| `BridgeVehicleHardware.cpp` | Generated | IVehicleHardware bridge impl |
| `FlyncDaemon.cpp` | Generated | Signal pack/unpack + transport |
| `Read_App_Signal_Data.cpp` | SDK ref | App-layer signal read API |
| `Write_App_Signal_Data.cpp` | SDK ref | App-layer signal write API |
| `iodata.cc` | SDK ref | CAN I/O data serialization |
| `ComConfig.cpp` | SDK ref | COM layer configuration |
| `CanConfig.cpp` | SDK ref | CAN configuration |
| `com_utils.cpp` | SDK ref | COM utility functions |

### Stub Headers

Minimal stubs in `vhal_gen/stubs/` shadow missing AOSP headers:

| Stub | Shadows |
|------|---------|
| `VehicleHalTypes.h` | 100+ AIDL-generated headers (StatusCode, VehiclePropValue, etc.) |
| `IVehicleHardware.h` | Wrapper that includes VehicleHalTypes.h |
| `android-base/logging.h` | Android logging (LOG/ALOGI/ALOGE as no-ops) |
| `json/json.h` | jsoncpp (Json::Value, Json::CharReaderBuilder) |

All stubs match the exact Android 14 (`android-14.0.0_r1`) AIDL interface definitions.

### Usage

```bash
# CLI
vhal-gen compile-check --vhal-dir <vhal-tree> --sdk-dir <sdk-src>

# Streamlit UI
# "Compile Check (Stubs)" button in Section 4
```

---

## AOSP Source Locations (Android 14)

```
hardware/interfaces/automotive/vehicle/
├── aidl/
│   ├── android/hardware/automotive/vehicle/
│   │   └── *.aidl                          # AIDL definitions
│   └── impl/
│       ├── default/
│       │   ├── DefaultVehicleHal.h/.cpp    # Main HAL implementation
│       │   └── VehicleService.cpp          # Service entry point (we replace)
│       ├── fake/
│       │   └── FakeVehicleHardware.h/.cpp  # Reference (we replace this)
│       ├── hardware/include/
│       │   └── IVehicleHardware.h          # Interface we implement
│       ├── utils/common/include/
│       │   └── VehicleHalTypes.h           # AIDL type umbrella header
│       └── config/
│           └── DefaultProperties.json      # Property configs (we generate)
```

## Key AOSP Interfaces

### IVehicleHardware (we implement this)

**Namespace:** `android::hardware::automotive::vehicle`

```cpp
class IVehicleHardware {
public:
    virtual std::vector<VehiclePropConfig> getAllPropertyConfigs() const = 0;
    virtual StatusCode getValues(
        std::shared_ptr<const GetValuesCallback> callback,
        const std::vector<GetValueRequest>& requests) const = 0;
    virtual StatusCode setValues(
        std::shared_ptr<const SetValuesCallback> callback,
        const std::vector<SetValueRequest>& requests) = 0;
    virtual DumpResult dump(const std::vector<std::string>& options) = 0;
    virtual StatusCode checkHealth() = 0;
    virtual void registerOnPropertyChangeEvent(
        std::unique_ptr<const PropertyChangeCallback> callback) = 0;
    virtual void registerOnPropertySetErrorEvent(
        std::unique_ptr<const PropertySetErrorCallback> callback) = 0;
    // Non-pure virtual with default no-op:
    virtual StatusCode updateSampleRate(int32_t propId, int32_t areaId,
                                        float sampleRate) { return StatusCode::OK; }
};
```

**Important:** `IVehicleHardware` does NOT have `subscribe()` or `unsubscribe()`.
Those methods exist on `DefaultVehicleHal` (the AIDL binder class), not on the
hardware abstraction layer.

### DefaultProperties.json Format (AOSP Compatible)

```json
{
    "apiVersion": 1,
    "properties": [
        {
            "property": "VehicleProperty::HEADLIGHTS_SWITCH",
            "propertyId": 289410828,
            "defaultValue": {"int32Values": [0]},
            "areas": [{"areaId": 0, "minInt32Value": 0, "maxInt32Value": 3}],
            "access": "VehiclePropertyAccess::READ",
            "changeMode": "VehiclePropertyChangeMode::ON_CHANGE"
        }
    ]
}
```

The `apiVersion` + `properties` wrapper matches the AOSP `JsonConfigLoader`
format. Each entry also carries a numeric `propertyId` field for reliable
parsing without needing AOSP's constant resolution.

### VehicleService.cpp (Entry Point)

```cpp
auto hardware = std::make_unique<BridgeVehicleHardware>();
auto vhal = ::ndk::SharedRefBase::make<DefaultVehicleHal>(std::move(hardware));
AServiceManager_addService(vhal->asBinder().get(), instance.c_str());
```

This is the only wiring point — `DefaultVehicleHal` takes ownership of
`IVehicleHardware` and calls its methods. The generated `VehicleService.cpp`
replaces the stock one that instantiates `FakeVehicleHardware`.
