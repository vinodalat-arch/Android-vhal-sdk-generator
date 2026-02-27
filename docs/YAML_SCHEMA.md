# FLYNC YAML Schema Reference

## File Types

| File | Location | Purpose |
|------|----------|---------|
| `system_metadata.flync.yaml` | Root | Version, OEM, platform metadata |
| `channels.yaml` | `general/channels/` | CAN bus topology, message routing |
| `*.flync.yaml` (PDU) | `general/channels/pdus/` | Signal definitions within PDUs |
| `vsm_states.flync.yaml` | `general/` | Vehicle global state definitions |
| `vsm_api.flync.yaml` | `general/` | VSM API service definitions |
| `ecu_metadata.flync.yaml` | `ecus/<name>/` | ECU authorship metadata |
| `ports.flync.yaml` | `ecus/<name>/` | Network port configuration |
| `*_controller.flync.yaml` | `ecus/<name>/controllers/` | ECU interface/gateway config |
| `socket_vsm.flync.yaml` | `ecus/<name>/sockets/` | VSM socket configuration |

---

## PDU File Schema

Location: `general/channels/pdus/<pdu_name>.flync.yaml`

```yaml
meta:
  author: <string>                    # Author name
  compatible_flync_version:
    version_schema: semver
    version: "1.0.0"

name: <string>                        # PDU name (matches filename without extension)
length: <int>                         # PDU length in bytes (e.g., 8 for CAN frame)
type: standard                        # PDU type (always "standard")
id: <hex>                             # Unique PDU ID (e.g., 0x401)

signals:
  - signal:
      name: <string>                  # Signal name (e.g., "u8_TurnLight_req")
      description: <string>           # Human-readable description
      bit_length: <int>               # Signal width in bits (1-32)
      base_data_type: <enum>          # bool | uint8 | uint16 | uint32
      endianness: <enum>              # little | big
      scale: <number>                 # Scaling factor (optional, default 1)
      offset: <number>               # Offset value (optional, default 0)
      lower_limit: <number>           # Minimum raw value
      upper_limit: <number>           # Maximum raw value
      compu_methods: [<string>]       # Computation methods (optional, e.g., ["crc16"])

      value_table:                    # Optional enumeration mapping
        - num_value: <int>
          description: <string>       # Enum name (e.g., "IL_IDLE", "LEFT")
```

### Signal Naming Convention
- `bo_` prefix: Boolean signal (1 bit typically)
- `u8_` prefix: Unsigned 8-bit signal
- `u16_` prefix: Unsigned 16-bit signal
- `_req` suffix: Request (typically RX from IVI perspective)
- `_cmd` suffix: Command (typically TX from IVI perspective)
- `_Sts`/`_sts` suffix: Status signal
- `_Sw` suffix: Switch input

### Start Bit Computation
PDU files specify `bit_length` but NOT `start_bit`. Start bits are computed by
sequential accumulation in signal order:

```
Signal 0: start_bit = 0,  bit_length = 3  → occupies bits 0-2
Signal 1: start_bit = 3,  bit_length = 1  → occupies bit 3
Signal 2: start_bit = 4,  bit_length = 2  → occupies bits 4-5
...
```

This matches the reference implementation in `ComConfig.cpp`.

---

## channels.yaml Schema

Location: `general/channels/channels.yaml`

```yaml
channels:
  - name: <string>                    # Channel name (e.g., "FD_CAN_ZC_FL_0")
    protocol:
      type: can_fd                    # Protocol: can_fd | can | lin
      bus_hw_id: <int>                # Hardware bus identifier (0-5)
      messages:
        - name: <string>             # Message name (e.g., "can_frame_0")
          id: <hex>                   # CAN frame ID (e.g., 0x00000560)
          protocol: can               # Wire protocol
          sender: <string>            # Sending ECU/controller name
          receivers: [<string>]       # List of receiving ECU/controller names
          pdu:
            pdu: <hex>                # Reference to PDU ID (e.g., 0x1560)
```

### Direction Determination (RX vs TX from IVI perspective)
- IVI is not an explicit ECU in the current model
- Direction is inferred from ECU roles:
  - Messages where `sender` is a vehicle ECU → **RX** (IVI receives)
  - Messages where `receivers` include vehicle ECUs → **TX** (IVI sends)
- Cross-reference: PDU ID in channels maps to PDU file by matching the `id` field

---

## vsm_states.flync.yaml Schema

```yaml
global_states:
  - name: <string>                    # State name (e.g., "deep_sleep", "parking")
    id: <int>                         # Numeric state ID
    participants: [<string>]          # ECUs active in this state
    is_default: <bool>                # Whether this is the default state
```

### Defined States
| ID | Name | Key Participants |
|----|------|-----------------|
| 1 | deep_sleep | hpc, zc_fr |
| 2 | parking | hpc, zc_fr, loris_10bt1s, cm_10bt1s |
| 3 | veh_off_user_off | hpc, zc_fr, cm_ilas, led_ilas |
| 4 | veh_on_user_on (DRIVING) | All ECUs (default state) |

---

## vsm_api.flync.yaml Schema

```yaml
meta:
  author: <string>
  compatible_flync_version:
    version_schema: semver
    version: "1.0.0"

vsm_api:
  services:
    - name: GlobalStateService
      id: <hex>                       # Service ID
      methods:
        - name: <string>             # Method name
          id: <hex>                   # Method ID
          direction: <enum>          # request | response
          payload:
            - name: <string>
              type: <string>         # Data type
              length: <int>          # Length in bytes
```

---

## ECU Controller Schema

Location: `ecus/<name>/controllers/<name>_controller.flync.yaml`

```yaml
name: <string>                        # Controller name
interfaces:
  - name: <string>                    # Interface name
    mac_address: <string>             # MAC address
    mii_config:
      type: sgmii                     # MII type
      speed: <int>                    # Speed in Mbps
      mode: mac                       # Mode
    virtual_interfaces:
      - name: vsm
        vlanid: <int>                 # VLAN ID (11 for VSM)
        addresses:
          - address: <ipv4>           # IP address
            ipv4netmask: <ipv4>       # Subnet mask

gateway:
  - type: can_to_eth                  # Gateway type
    source_bus: <string>              # CAN bus name from channels.yaml
    source_frame_id: <hex>            # CAN frame ID
    target_container_id: <int>        # Ethernet container ID
```

---

## Known PDU Files

| File | PDU ID | Length | Signals | Role |
|------|--------|--------|---------|------|
| ExteriorLighting_Doors_Req | 0x401 | 8 bytes | 15 | Primary RX (requests from vehicle) |
| ExteriorLighting_Doors_Cmd | 0x101 | 8 bytes | 20 | Primary TX (commands to vehicle) |
| power_status_front_right_pdu | 0x403FF10 | 1 byte | 2 | RX power status |
| power_control_front_right_pdu | 0x103FFFE | 1 byte | 2 | TX power control |
| test_switch_global_state_pdu | 0x560 | 2 bytes | 2 | Global state test |
| ecu_control_message_pdu | 0x300 | 3 bytes | 3 | ECU control |
