# wattcycle-ble

A Python library and CLI for communicating with XDZN/Wattcycle BLE battery management systems.

Protocol reverse-engineered from the `com.gz.wattcycle` Android app. See [PROTOCOL.md](PROTOCOL.md) for the full protocol specification.

## Tested Devices

| Device | Firmware | Cells | Notes |
|--------|----------|-------|-------|
| XDZN_001_EF2F | WT12_20004SW10_L447 | 4S LiFePO4 | 314 Ah |

If you have a different Wattcycle/XDZN device, please open an issue with your results.

## Installation

```bash
pip install wattcycle-ble
```

Or from source:

```bash
git clone https://github.com/luke/wattcycle-ble.git
cd wattcycle-ble
pip install -e .
```

## CLI Usage

Scan for devices:

```bash
wattcycle-ble scan
```

Read battery data:

```bash
wattcycle-ble read C0:D6:3C:57:EF:2F
```

Continuously poll (every 5 seconds):

```bash
wattcycle-ble loop C0:D6:3C:57:EF:2F --interval 5
```

Add `-v` for debug logging:

```bash
wattcycle-ble -v read C0:D6:3C:57:EF:2F
```

## Library Usage

```python
import asyncio
from wattcycle_ble import WattcycleClient

async def main():
    async with WattcycleClient("C0:D6:3C:57:EF:2F") as client:
        await client.detect_frame_head()

        info = await client.read_product_info()
        print(f"Firmware: {info.firmware_version}")
        print(f"Serial:   {info.serial_number}")

        data = await client.read_analog_quantity()
        print(f"SOC: {data.soc}%")
        print(f"Voltage: {data.module_voltage:.2f} V")
        print(f"Current: {data.current:.1f} A")
        print(f"Capacity: {data.remaining_capacity:.1f} / {data.total_capacity:.1f} Ah")

        for i, v in enumerate(data.cell_voltages):
            print(f"  Cell {i+1}: {v:.3f} V")

        warnings = await client.read_warning_info()
        if warnings.protections:
            print(f"Active protections: {warnings.protections}")

asyncio.run(main())
```

### Scanning for Devices

```python
devices = await WattcycleClient.scan(timeout=10.0)
for d in devices:
    print(f"{d.name} ({d.address})")
```

## Protocol

The full BLE protocol documentation is in [PROTOCOL.md](PROTOCOL.md).

Key points:
- BLE service `0xFFF0` with write (`FFF2`), notify (`FFF1`), and auth (`FFFA`) characteristics
- Authentication: write `HiLink` to `FFFA`
- Modbus-like framing with CRC16
- No pairing required

## Requirements

- Python 3.11+
- [bleak](https://github.com/hbldh/bleak) (BLE library)
- Linux, macOS, or Windows with Bluetooth support

## License

MIT
# wattcycle_ble
