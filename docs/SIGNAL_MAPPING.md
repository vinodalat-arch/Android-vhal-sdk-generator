# Signal → VehicleProperty Mapping

## Mapping Strategy

Signals are mapped in priority order:
1. **Exact match** — signal name maps to a known AOSP VehicleProperty
2. **Vendor fallback** — remaining signals get vendor property IDs

No keyword/fuzzy matching is used. This keeps the mapping fully deterministic and
auditable.

---

## Exact Matches (11 signals → AOSP Standard Properties)

| Signal Name | PDU | Dir | AOSP Property | Property ID | Notes |
|-------------|-----|-----|---------------|-------------|-------|
| `u8_MainLightSelector_Req` | 0x401 | RX | HEADLIGHTS_SWITCH | 0x0E010A00 | 2-bit enum |
| `u8_MainLightSelector_Status` | 0x101 | TX | HEADLIGHTS_STATE | 0x0E010A01 | 2-bit enum |
| `u8_HighBeam` | 0x101 | TX | HIGH_BEAM_LIGHTS_STATE | 0x0E010A02 | Derived from beam status |
| `u8_Beam_Req` | 0x401 | RX | HIGH_BEAM_LIGHTS_SWITCH | 0x0E010A03 | 2-bit enum |
| `u8_TurnLight_req` | 0x401 | RX | TURN_SIGNAL_STATE | 0x0E010A04 | 3-bit enum (0-5) |
| `u8_HazardLight_req` | 0x401 | RX | HAZARD_LIGHTS_SWITCH | 0x0E010A05 | 2-bit enum |
| `bo_HazardLight_cmd` | 0x101 | TX | HAZARD_LIGHTS_STATE | 0x0E010A06 | Boolean |
| `bo_DoorLock_Sw` | 0x401 | RX | DOOR_LOCK | 0x0E010B00 | area=GLOBAL |
| `bo_FR_Unlock_Sts` | 0x101 | TX | DOOR_LOCK | 0x0E010B00 | area=ROW_1_RIGHT |
| `bo_FL_Unlock_Sts` | 0x101 | TX | DOOR_LOCK | 0x0E010B00 | area=ROW_1_LEFT |
| `bo_RR_Unlock_Sts` | 0x101 | TX | DOOR_LOCK | 0x0E010B00 | area=ROW_2_RIGHT |
| `bo_RL_Unlock_Sts` | 0x101 | TX | DOOR_LOCK | 0x0E010B00 | area=ROW_2_LEFT |
| `u8_VehSpd_kmph` | 0x401 | RX | PERF_VEHICLE_SPEED | 0x11600207 | Convert km/h→m/s (÷3.6) |
| `u8_ALS_Data` | 0x401 | RX | NIGHT_MODE | 0x11200407 | Map: 0=day, 1=night |

---

## Vendor Properties (~26 signals)

Vendor property IDs are constructed as:
```
vendor_id = unique_counter | VehiclePropertyGroup.VENDOR (0x20000000)
                           | VehicleArea
                           | VehiclePropertyType
```

| Signal Name | PDU | Dir | Vendor ID | Type | Access |
|-------------|-----|-----|-----------|------|--------|
| `bo_DRL_cmd` | 0x101 | TX | 0x20100101 | BOOLEAN | READ |
| `bo_Crash_Detection_sts` | 0x401 | RX | 0x20100102 | BOOLEAN | READ |
| `bo_Crash_Detection_cmd` | 0x101 | TX | 0x20100103 | BOOLEAN | READ |
| `bo_RKE_Authentication_Status` | 0x401 | RX | 0x20100104 | BOOLEAN | READ |
| `bo_BattVg_AbvTH` | 0x401 | RX | 0x20100105 | BOOLEAN | READ |
| `bo_ChldLck_DrSW` | 0x401 | RX | 0x20100106 | BOOLEAN | READ |
| `bo_DoorKey_req` | 0x401 | RX | 0x20100107 | BOOLEAN | READ |
| `u8_RainLightSensor_Data` | 0x401 | RX | 0x20400108 | INT32 | READ |
| `u8_BlinkFreq_Req` | 0x401 | RX | 0x20400109 | INT32 | READ |
| `bo_Indicator_Buzzer_Sts` | 0x101 | TX | 0x2010010A | BOOLEAN | READ |
| `bo_FrontRight_Light_cmd` | 0x101 | TX | 0x2010010B | BOOLEAN | READ |
| `bo_FrontLeft_Light_cmd` | 0x101 | TX | 0x2010010C | BOOLEAN | READ |
| `bo_RearRight_Light_cmd` | 0x101 | TX | 0x2010010D | BOOLEAN | READ |
| `bo_RearLeft_Light_cmd` | 0x101 | TX | 0x2010010E | BOOLEAN | READ |
| `bo_MirrorRight_Light_cmd` | 0x101 | TX | 0x2010010F | BOOLEAN | READ |
| `bo_MirrorLeft_Light_cmd` | 0x101 | TX | 0x20100110 | BOOLEAN | READ |
| `bo_Right_Ind_Display_Sts` | 0x101 | TX | 0x20100111 | BOOLEAN | READ |
| `bo_Left_Ind_Display_Sts` | 0x101 | TX | 0x20100112 | BOOLEAN | READ |
| `u8_LowBeam` | 0x101 | TX | 0x20400113 | INT32 | READ |
| `u8_Beam_Req_Status` | 0x101 | TX | 0x20400114 | INT32 | READ |
| `global_state_value` | 0x560 | RX | 0x20400115 | INT32 | READ |
| `ext_wake_inputs` | 0x560 | RX | 0x20400116 | INT32 | READ |
| `power_status` | 0x403FF10 | RX | 0x20400117 | INT32 | READ |
| `power_control` | 0x103FFFE | TX | 0x20400118 | INT32 | READ_WRITE |
| `ecu_reset` | 0x300 | TX | 0x20100119 | BOOLEAN | READ_WRITE |

*Note: Exact vendor IDs will be computed by `vendor_id_allocator.py` at generation time.*

---

## AOSP Property ID Structure (Android 14)

```
Property ID = [Group:4][Area:4][Type:4][Property:20] (32-bit)

VehiclePropertyGroup:
  SYSTEM  = 0x10000000
  VENDOR  = 0x20000000

VehicleArea:
  GLOBAL  = 0x01000000
  WINDOW  = 0x03000000
  DOOR    = 0x06000000
  SEAT    = 0x05000000
  WHEEL   = 0x07000000

VehiclePropertyType:
  BOOLEAN = 0x00200000
  INT32   = 0x00400000
  FLOAT   = 0x00600000
  INT64   = 0x00500000
  STRING  = 0x00100000
```

---

## Access Modes

| Mode | Value | Description |
|------|-------|-------------|
| READ | 1 | Property can only be read (RX signals) |
| WRITE | 2 | Property can only be written |
| READ_WRITE | 3 | Property can be read and written (bidirectional signals) |

## Change Modes

| Mode | Value | Description |
|------|-------|-------------|
| STATIC | 0 | Value never changes after boot |
| ON_CHANGE | 1 | Notify on value change (default for most signals) |
| CONTINUOUS | 2 | Notify at fixed rate (used for speed, etc.) |
