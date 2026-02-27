# Vehicle Network & Communication Model

## ECU Topology

```
                    ┌─────────────┐
                    │     HPC     │ High Performance Controller
                    │ (Gateway)   │ CAN-to-Ethernet bridge
                    └──────┬──────┘
                           │ Ethernet (VLAN 11)
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌───▼───┐ ┌─────▼─────┐
        │  ZC_FL    │ │ ZC_FR │ │  IVI      │
        │ Zone Ctrl │ │ Zone  │ │ (Android) │
        │ Front-Left│ │ Ctrl  │ │           │
        └─────┬─────┘ └───┬───┘ └───────────┘
              │            │
        ┌─────▼─────┐ ┌───▼────────┐
        │ CM_ILAS   │ │ CM_10BT1S  │
        │ LED_ILAS  │ │ LORIS      │
        └───────────┘ └────────────┘
```

## Communication Model

### CAN FD Buses
Each ECU pair communicates over CAN FD with hardware bus IDs 0-5:
- `FD_CAN_ZC_FL_0` through `FD_CAN_ZC_FL_5` — ZC_FL buses
- `FD_CAN_ZC_FR_0` through `FD_CAN_ZC_FR_5` — ZC_FR buses

### CAN-to-Ethernet Gateway
ECU controllers bridge CAN frames to Ethernet via gateway configs:
```
CAN Frame (bus: FD_CAN_ZC_FL_0, ID: 0x560)
    → Gateway (can_to_eth)
    → Ethernet Container (VLAN 11, UDP)
    → HPC FDN Router
    → IVI (Android)
```

### IVI Communication Path
```
IVI ←→ HPC FDN Router ←→ ECU CAN Buses

Transport: UDP over Ethernet VLAN 11
IP Range: 10.0.11.x/24
  - ZC_FL: 10.0.11.21
  - ZC_FR: 10.0.11.22
  - HPC:   10.0.11.1 (assumed gateway)
```

---

## PDU Catalog

### Primary PDUs (Body/Lighting)

| PDU Name | ID | Length | Signals | Direction | CAN IDs |
|----------|----|--------|---------|-----------|---------|
| ExteriorLighting_Doors_Req | 0x401 | 8 bytes | 15 | RX | 0x1401 |
| ExteriorLighting_Doors_Cmd | 0x101 | 8 bytes | 20 | TX | 0x1101 |

### System PDUs

| PDU Name | ID | Length | Signals | Direction | CAN IDs |
|----------|----|--------|---------|-----------|---------|
| test_switch_global_state_pdu | 0x560 | 2 bytes | 2 | RX | 0x00000560 |
| power_status_front_right_pdu | 0x403FF10 | 1 byte | 2 | RX | 0x1403FF10 |
| power_control_front_right_pdu | 0x103FFFE | 1 byte | 2 | TX | 0x1403FFFE |
| ecu_control_message_pdu | 0x300 | 3 bytes | 3 | TX | — |

---

## Wire Format

### CAN Frame Structure
```
┌──────────┬────────┬──────────┐
│ CAN ID   │ DLC    │ Data     │
│ 11/29bit │ 0-8    │ 0-8 bytes│
└──────────┴────────┴──────────┘
```

### Signal Packing (Little-Endian / Intel byte order)
Signals are packed LSB-first within the data bytes:

```
Example: ExteriorLighting_Doors_Req (8 bytes = 64 bits)

Byte:  [0]      [1]      [2]      [3]      [4]      [5-7]
Bits:  76543210 76543210 76543210 76543210 76543210 ...

Bit 0-2:   u8_TurnLight_req (3 bits)
Bit 3:     bo_Crash_Detection_sts (1 bit)
Bit 4-5:   u8_PowerModeStatus (2 bits)
Bit 6:     bo_RKE_Authentication_Status (1 bit)
Bit 7:     bo_BattVg_AbvTH (1 bit)
Bit 8-9:   u8_ALS_Data (2 bits)
Bit 10-11: u8_Beam_Req (2 bits)
Bit 12-13: u8_MainLightSelector_Req (2 bits)
Bit 14-15: u8_HazardLight_req (2 bits)
Bit 16-17: bo_ChldLck_DrSW (2 bits)
Bit 18-19: bo_DoorLock_Sw (2 bits)
Bit 20-21: bo_DoorKey_req (2 bits)
Bit 22-23: u8_RainLightSensor_Data (2 bits)
Bit 24-31: u8_VehSpd_kmph (8 bits)
Bit 32-39: u8_BlinkFreq_Req (8 bits)
```

### Unpack Algorithm (from reference com_utils.cpp)
```
uint32_t unpack_signal(buffer, start_bit, length):
    value = 0
    for i in 0..length-1:
        bit_index = start_bit + i
        byte = bit_index / 8
        bit = bit_index % 8
        bit_val = (buffer[byte] >> bit) & 1
        value |= (bit_val << i)
    return value & ((1 << length) - 1)
```

### Pack Algorithm (from reference com_utils.cpp)
```
pack_signal(buffer, start_bit, length, value):
    value &= ((1 << length) - 1)
    for i in 0..length-1:
        dest_bit = start_bit + i
        byte = dest_bit / 8
        bit_in_byte = dest_bit % 8
        bit_val = (value >> i) & 1
        if bit_val:
            buffer[byte] |= (1 << bit_in_byte)
        else:
            buffer[byte] &= ~(1 << bit_in_byte)
```

---

## UDP Transport Configuration

### For Live Vehicle Network
```
Protocol: UDP
VLAN: 11
IVI IP: 10.0.11.x (assigned by DHCP or static config)
HPC Gateway: 10.0.11.1 (FDN Router)
Port: TBD (configurable, default 5555)
```

### PDU-over-UDP Framing
Each UDP packet carries one or more PDU frames:
```
┌──────────┬──────────┬──────────┐
│ PDU ID   │ Length   │ Data     │
│ 4 bytes  │ 2 bytes  │ N bytes  │
└──────────┴──────────┴──────────┘
```

### Mock Transport (Emulator)
- Loopback UDP or in-process simulation
- Generates periodic signal updates with cycling values
- Used for development and testing without vehicle hardware
