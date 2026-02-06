# Wattcycle BLE Protocol Documentation

Reverse-engineered from the `com.gz.wattcycle` Android APK (decompiled with jadx).

**OEM:** XDZN (Xiao Dian Zhi Neng / 小电智能)
**Device prefix:** `XDZN` or `WT`
**Protocol type:** WATT (vs JDY for JDY-prefixed devices)

---

## BLE GATT Structure

| Characteristic | UUID                                   | Role            |
|----------------|----------------------------------------|-----------------|
| Service        | `0000fff0-0000-1000-8000-00805f9b34fb` | Main service    |
| Write          | `0000fff2-0000-1000-8000-00805f9b34fb` | Send commands   |
| Notify         | `0000fff1-0000-1000-8000-00805f9b34fb` | Receive data    |
| Auth           | `0000fffa-0000-1000-8000-00805f9b34fb` | Authentication  |

No pairing/bonding required.

---

## Authentication

Write `HiLink` (6 bytes, UTF-8: `48 69 4C 69 6E 6B`) to the **Auth** characteristic (`FFFA`) immediately after connecting.

---

## Frame Format

All frames use **Big-Endian** byte ordering.

### Request Frame (Read)

```
[HEAD] [VER] [ADDR] [FUNC] [START_ADDR:2] [READ_COUNT:2] [INFO_DATA...] [CRC16:2] [TAIL]
```

| Field       | Bytes | Value                                        |
|-------------|-------|----------------------------------------------|
| HEAD        | 1     | `0x7E` (default) or `0x1E` (alternative)     |
| VER         | 1     | `0x00` (old protocol) or `0x01` (if infoData present) |
| ADDR        | 1     | `0x01` (device address)                      |
| FUNC        | 1     | `0x03` (read)                                |
| START_ADDR  | 2     | DP address (big-endian uint16)               |
| READ_COUNT  | 2     | Number of registers to read (big-endian uint16) |
| INFO_DATA   | 0 or 7| Optional, present only for new protocol version |
| CRC16       | 2     | Modbus CRC16 over bytes 0..(length-3)        |
| TAIL        | 1     | `0x0D`                                       |

**Minimum frame size:** 11 bytes (without infoData).

### Request Frame (Write)

```
[HEAD] [VER] [ADDR] [FUNC] [START_ADDR:2] [DATA_LEN:2] [DATA...] [CRC16:2] [TAIL]
```

| Field       | Bytes | Value                        |
|-------------|-------|------------------------------|
| HEAD        | 1     | `0x7E`                       |
| VER         | 1     | `0x00`                       |
| ADDR        | 1     | `0x01`                       |
| FUNC        | 1     | `0x06` (write)               |
| START_ADDR  | 2     | DP address (big-endian)      |
| DATA_LEN    | 2     | Length of DATA (big-endian)  |
| DATA        | N     | Payload bytes                |
| CRC16       | 2     | Modbus CRC16 over bytes 0..(length-3) |
| TAIL        | 1     | `0x0D`                       |

### Response Frame

```
[HEAD] [VER] [ADDR] [FUNC] [START_ADDR:2] [DATA_LEN:2] [DATA...] [CRC16:2] [TAIL]
```

Same structure as request. Function code `0x86` (decimal -122 as signed byte) indicates an error.

**Expected response length** = `DATA_LEN` (bytes 6-7, unsigned) + 11.

**Version detection:** If response VER byte >= 4, the device uses the "new version" protocol.

---

## Modbus CRC16

Standard Modbus CRC16 using lookup tables. Calculated over all bytes from HEAD up to (but not including) the CRC16 field itself.

Initial values: `crc_hi = 0xFF`, `crc_lo = 0xFF`.

```python
def modbus_crc16(data: bytes) -> int:
    crc_hi = 0xFF
    crc_lo = 0xFF
    for byte in data:
        index = crc_hi ^ byte
        crc_hi = crc_lo ^ CRC_HI_TABLE[index]
        crc_lo = CRC_LO_TABLE[index]
    return (crc_lo << 8) | crc_hi
```

Note: The result is `(lo << 8) | hi`, which is then written as a big-endian uint16 into the frame.

---

## DP Addresses (Data Points)

| Address | Hex    | Name                   | Direction |
|---------|--------|------------------------|-----------|
| 1       | 0x0001 | Battery Temperature    | Read      |
| 30      | 0x001E | Collection Board       | Read      |
| 50      | 0x0032 | Cell Characteristics   | Read      |
| 70      | 0x0046 | Protection Parameters  | Read      |
| 120     | 0x0078 | Get Password           | Read      |
| 121     | 0x0079 | Input Password         | Write     |
| 122     | 0x007A | Change Password        | Write     |
| 130     | 0x0082 | Charge/Discharge Switch| Write     |
| 131     | 0x0083 | Restart System         | Write     |
| 132     | 0x0084 | Restore Defaults       | Write     |
| 133     | 0x0085 | Factory Reset          | Write     |
| 134     | 0x0086 | Reset                  | Write     |
| **140** | **0x008C** | **Analog Quantity** (main battery data) | **Read** |
| **141** | **0x008D** | **Warning Info**    | **Read**  |
| **146** | **0x0092** | **Product Info**    | **Read**  |

---

## InfoData Structure (New Protocol)

When using the new protocol (version=1), an additional 7-byte infoData block is appended to read frames:

```
[0x00 0x05] [ADDRESS:1] [VOLTAGE_COUNT:2] [TEMPERATURE_COUNT:2]
```

For Analog Quantity reads: `buildInfoData(1, 32, 32)` = `00 05 01 00 20 00 20`

---

## Response Parsing: Analog Quantity (DP 140 / 0x8C)

The main battery status data. Parsing order within the DATA portion:

| Offset | Type   | Field              | Conversion                        |
|--------|--------|--------------------|-----------------------------------|
| 0      | uint8  | cellCount          | Raw value                         |
| 1..    | uint16 | cellVoltages[]     | `value / 1000.0` (volts), repeated `cellCount` times |
| next   | uint8  | temperatureCount   | Raw value                         |
| next   | uint16 | mosTemperature     | `(value - 2730) / 10.0` (°C)     |
| next   | uint16 | pcbTemperature     | `(value - 2730) / 10.0` (°C)     |
| next   | uint16 | cellTemperatures[] | `(value - 2730) / 10.0` (°C), repeated `(tempCount - 2)` times |
| next   | custom | current            | See "Current Parsing" below       |
| next   | uint16 | moduleVoltage      | `value / 100.0` (volts)           |
| next   | uint16 | remainingCapacity  | `value / 10.0` (Ah)              |
| next   | uint16 | totalCapacity      | `value / 10.0` (Ah)              |
| next   | uint16 | cycleNumber        | Raw value                         |
| next   | uint16 | designCapacity     | `value / 10.0` (Ah)              |
| next   | uint16 | soc                | Percentage (0-100)                |

### New Version Extension (if >= 18 bytes remaining)

| Offset | Type   | Field              | Conversion                        |
|--------|--------|--------------------|-----------------------------------|
| next   | uint16 | soh                | Percentage                        |
| next   | uint32 | cumulativeCapacity | `value / 10.0` (Ah)              |
| next   | int32  | remainingTime      | Minutes                           |
| next   | uint16 | (reserved)         |                                   |
| next   | uint16 | (reserved)         |                                   |
| next   | uint16 | (reserved)         |                                   |
| next   | custom | balanceCurrent     | See "Current Parsing (Negative)" below |

---

## Current Parsing

### parseWattCurrent (2 bytes)

```
byte0 = buffer[0]   (signed byte)
byte1 = buffer[1]   (unsigned byte, 0-255)

flag = (byte0 & 0xC0) >> 6
has_decimal = (flag == 1 or flag == 3)
raw_value = byte1 | ((byte0 & 0x3F) << 8)

if has_decimal:
    current = raw_value / 10.0
else:
    current = raw_value
```

### parseWattCurrentNegative (2 bytes)

Used for the main current reading in Analog Quantity.

```
byte0 = buffer[0]   (signed byte)
byte1 = buffer[1]   (unsigned byte, 0-255)

is_negative = (byte0 & 0x80) != 0    # bit 7: sign
has_decimal = (byte0 & 0x40) != 0    # bit 6: decimal flag
raw_value = byte1 | ((byte0 & 0x3F) << 8)

current = raw_value / 10.0 if has_decimal else raw_value
current = -current if is_negative else current
```

---

## Response Parsing: Warning Info (DP 141 / 0x8D)

| Offset | Type   | Field                | Notes                              |
|--------|--------|----------------------|------------------------------------|
| 0      | uint8  | cellCount            |                                    |
| 1..    | byte   | cellStates[]         | One byte per cell                  |
| next   | uint8  | temperatureCount     |                                    |
| next   | byte   | mosTemperatureState  |                                    |
| next   | byte   | pcbTemperatureState  |                                    |
| next   | byte   | cellTempStates[]     | `(tempCount - 2)` entries          |
| next   | byte   | chargeCurrentState   |                                    |
| next   | byte   | voltageState         |                                    |
| next   | byte   | dischargeCurrentState|                                    |
| next   | byte   | batteryMode          |                                    |
| next   | byte   | statusRegister1      | Protection flags (8 bits)          |
| next   | byte   | statusRegister2      | Temperature protection flags       |
| next   | byte   | statusRegister3      |                                    |
| next   | byte   | (reserved)           |                                    |
| next   | byte   | statusRegister5      | Fault flags (cell, MOS, temp)      |
| next   | byte   | (reserved)           |                                    |
| next   | byte   | (reserved)           |                                    |
| next   | byte   | warningRegister1     | Warning flags (8 bits)             |
| next   | byte   | warningRegister2     | Temperature warning flags          |
| next   | bytes  | balanceStates[]      | `ceil(cellCount/8)` bytes, bitfield|

### StatusRegister1 Bits

| Bit | Flag                           |
|-----|--------------------------------|
| 0   | Cell overcharge protection     |
| 1   | Cell overdischarge protection  |
| 2   | Total overcharge protection    |
| 3   | Total overdischarge protection |
| 4   | Charge overcurrent protection  |
| 5   | Discharge overcurrent protection|
| 6   | Hardware protection            |
| 7   | Charge voltage high            |

### StatusRegister2 Bits

| Bit | Flag                                  |
|-----|---------------------------------------|
| 0   | Charge high temperature protection    |
| 1   | Discharge high temperature protection |
| 2   | Charge low temperature protection     |
| 3   | Discharge low temperature protection  |
| 4   | MOS high temperature protection       |
| 5   | Environment high temperature protection|
| 6   | Environment low temperature protection|

### StatusRegister5 Bits (Faults)

| Bit | Flag                   |
|-----|------------------------|
| 0   | Cell fault             |
| 1   | Charge MOS fault       |
| 2   | Discharge MOS fault    |
| 3   | Temperature fault      |

---

## Response Parsing: Product Info (DP 146 / 0x0092)

Total data length must be exactly **60 bytes**.

| Offset | Length | Field            | Encoding    |
|--------|--------|------------------|-------------|
| 0      | 20     | firmwareVersion  | ASCII, null-trimmed |
| 20     | 20     | manufacturerName | ASCII, null-trimmed |
| 40     | 20     | serialNumber     | ASCII, null-trimmed |

---

## Connection Sequence

1. Scan for BLE devices with name prefix `XDZN` or `WT`
2. Connect to the device (no pairing required)
3. Discover services, find service `0xFFF0`
4. Enable notifications on `FFF1`
5. Write `HiLink` (`48 69 4C 69 6E 6B`) to `FFFA` (auth)
6. Detect frame header by trying `0x7E` then `0x1E` (3s timeout each)
7. Send read commands via `FFF2`, receive responses via `FFF1` notifications

---

## Example Commands

### Read Analog Quantity (old protocol)
```
TX: 7E 00 01 03 00 8C 00 00 [CRC_HI] [CRC_LO] 0D
```

### Read Warning Info (old protocol)
```
TX: 7E 00 01 03 00 8D 00 00 [CRC_HI] [CRC_LO] 0D
```

### Read Product Info (old protocol)
```
TX: 7E 00 01 03 00 92 00 00 [CRC_HI] [CRC_LO] 0D
```

### Read Analog Quantity (new protocol, with infoData)
```
TX: 7E 01 01 03 00 8C 00 00 00 05 01 00 20 00 20 [CRC_HI] [CRC_LO] 0D
```

---

## Packet Reassembly

BLE has a max MTU (~20 bytes default). Responses are split across multiple notifications. Use `calculateExpectedLength` on the first packet:

```
expected_length = uint16_be(packet[6:8]) + 11
```

Concatenate notification payloads until you reach `expected_length` bytes. Verify the last byte is `0x0D`.
