"""Wattcycle BLE protocol: frame building, parsing, and CRC.

This module has no external dependencies (no bleak) and can be used
standalone for offline frame analysis.
"""

from __future__ import annotations

import logging
import struct

from .models import AnalogQuantity, ProductInfo, WarningInfo, WattFrame

logger = logging.getLogger(__name__)

# --- BLE UUIDs ---
SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000fff2-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"
AUTH_UUID = "0000fffa-0000-1000-8000-00805f9b34fb"

# --- Protocol Constants ---
FRAME_HEAD = 0x7E
FRAME_HEAD_ALT = 0x1E
FRAME_TAIL = 0x0D
FUNC_READ = 0x03
FUNC_WRITE = 0x06
DEVICE_ADDR = 0x01
MIN_FRAME_SIZE = 11

AUTH_KEY = b"HiLink"
DEVICE_NAME_PREFIXES = ("XDZN", "WT")

# --- DP Addresses ---
DP_ANALOG_QUANTITY = 140  # 0x8C
DP_WARNING_INFO = 141     # 0x8D
DP_PRODUCT_INFO = 146     # 0x92

# --- Modbus CRC16 Lookup Tables ---
_CRC_HI = bytes([
    0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40,
    0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41,
    0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41,
    0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40,
    0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41,
    0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40,
    0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40,
    0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41,
    0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41,
    0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40,
    0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40,
    0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41,
    0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40,
    0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41,
    0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41,
    0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40,
])

_CRC_LO = bytes([
    0x00, 0xC0, 0xC1, 0x01, 0xC3, 0x03, 0x02, 0xC2, 0xC6, 0x06, 0x07, 0xC7, 0x05, 0xC5, 0xC4, 0x04,
    0xCC, 0x0C, 0x0D, 0xCD, 0x0F, 0xCF, 0xCE, 0x0E, 0x0A, 0xCA, 0xCB, 0x0B, 0xC9, 0x09, 0x08, 0xC8,
    0xD8, 0x18, 0x19, 0xD9, 0x1B, 0xDB, 0xDA, 0x1A, 0x1E, 0xDE, 0xDF, 0x1F, 0xDD, 0x1D, 0x1C, 0xDC,
    0x14, 0xD4, 0xD5, 0x15, 0xD7, 0x17, 0x16, 0xD6, 0xD2, 0x12, 0x13, 0xD3, 0x11, 0xD1, 0xD0, 0x10,
    0xF0, 0x30, 0x31, 0xF1, 0x33, 0xF3, 0xF2, 0x32, 0x36, 0xF6, 0xF7, 0x37, 0xF5, 0x35, 0x34, 0xF4,
    0x3C, 0xFC, 0xFD, 0x3D, 0xFF, 0x3F, 0x3E, 0xFE, 0xFA, 0x3A, 0x3B, 0xFB, 0x39, 0xF9, 0xF8, 0x38,
    0x28, 0xE8, 0xE9, 0x29, 0xEB, 0x2B, 0x2A, 0xEA, 0xEE, 0x2E, 0x2F, 0xEF, 0x2D, 0xED, 0xEC, 0x2C,
    0xE4, 0x24, 0x25, 0xE5, 0x27, 0xE7, 0xE6, 0x26, 0x22, 0xE2, 0xE3, 0x23, 0xE1, 0x21, 0x20, 0xE0,
    0xA0, 0x60, 0x61, 0xA1, 0x63, 0xA3, 0xA2, 0x62, 0x66, 0xA6, 0xA7, 0x67, 0xA5, 0x65, 0x64, 0xA4,
    0x6C, 0xAC, 0xAD, 0x6D, 0xAF, 0x6F, 0x6E, 0xAE, 0xAA, 0x6A, 0x6B, 0xAB, 0x69, 0xA9, 0xA8, 0x68,
    0x78, 0xB8, 0xB9, 0x79, 0xBB, 0x7B, 0x7A, 0xBA, 0xBE, 0x7E, 0x7F, 0xBF, 0x7D, 0xBD, 0xBC, 0x7C,
    0xB4, 0x74, 0x75, 0xB5, 0x77, 0xB7, 0xB6, 0x76, 0x72, 0xB2, 0xB3, 0x73, 0xB1, 0x71, 0x70, 0xB0,
    0x50, 0x90, 0x91, 0x51, 0x93, 0x53, 0x52, 0x92, 0x96, 0x56, 0x57, 0x97, 0x55, 0x95, 0x94, 0x54,
    0x9C, 0x5C, 0x5D, 0x9D, 0x5F, 0x9F, 0x9E, 0x5E, 0x5A, 0x9A, 0x9B, 0x5B, 0x99, 0x59, 0x58, 0x98,
    0x88, 0x48, 0x49, 0x89, 0x4B, 0x8B, 0x8A, 0x4A, 0x4E, 0x8E, 0x8F, 0x4F, 0x8D, 0x4D, 0x4C, 0x8C,
    0x44, 0x84, 0x85, 0x45, 0x87, 0x47, 0x46, 0x86, 0x82, 0x42, 0x43, 0x83, 0x41, 0x81, 0x80, 0x40,
])


def modbus_crc16(data: bytes) -> int:
    """Calculate Modbus CRC16 using lookup tables.

    Uses the same algorithm as the Wattcycle APK (init 0xFF/0xFF,
    result is ``(lo << 8) | hi``).
    """
    crc_hi = 0xFF
    crc_lo = 0xFF
    for b in data:
        idx = crc_hi ^ b
        crc_hi = crc_lo ^ _CRC_HI[idx]
        crc_lo = _CRC_LO[idx]
    return ((crc_lo << 8) | crc_hi) & 0xFFFF


def build_read_frame(
    address: int,
    read_count: int = 0,
    frame_head: int = FRAME_HEAD,
) -> bytes:
    """Build a read command frame (old protocol, no infoData).

    Args:
        address: DP address to read (e.g. ``DP_ANALOG_QUANTITY``).
        read_count: Number of registers to read (usually 0).
        frame_head: Frame header byte (``0x7E`` or ``0x1E``).

    Returns:
        Complete frame bytes ready to send.
    """
    buf = bytearray()
    buf.append(frame_head)
    buf.append(0x00)           # version (old protocol)
    buf.append(DEVICE_ADDR)
    buf.append(FUNC_READ)
    buf.extend(struct.pack(">H", address))
    buf.extend(struct.pack(">H", read_count))
    crc = modbus_crc16(bytes(buf))
    buf.extend(struct.pack(">H", crc))
    buf.append(FRAME_TAIL)
    return bytes(buf)


def verify_crc(data: bytes) -> bool:
    """Verify the CRC16 of a complete frame."""
    if len(data) < MIN_FRAME_SIZE:
        return False
    payload = data[:-3]  # everything except CRC(2) + TAIL(1)
    expected_crc = struct.unpack(">H", data[-3:-1])[0]
    return modbus_crc16(payload) == expected_crc


def expected_response_length(first_packet: bytes) -> int | None:
    """Calculate expected total response length from the first packet.

    Returns ``None`` if the packet is too short to determine.
    """
    if len(first_packet) < 8:
        return None
    data_len = struct.unpack(">H", first_packet[6:8])[0]
    return data_len + 11


def parse_frame(data: bytes) -> WattFrame | None:
    """Parse a complete response frame.

    Returns ``None`` if the frame is invalid or an error response.
    """
    if len(data) < MIN_FRAME_SIZE:
        logger.warning("Frame too short: %d bytes", len(data))
        return None
    if data[0] not in (FRAME_HEAD, FRAME_HEAD_ALT):
        logger.warning("Invalid frame head: 0x%02X", data[0])
        return None
    if data[-1] != FRAME_TAIL:
        logger.warning("Invalid frame tail: 0x%02X", data[-1])
        return None

    func = data[3]
    if func == 0x86:
        logger.warning("Device returned error (function code 0x86)")
        return None

    if not verify_crc(data):
        logger.warning("CRC mismatch")

    start_addr = struct.unpack(">H", data[4:6])[0]
    data_len = struct.unpack(">H", data[6:8])[0]

    return WattFrame(
        version=data[1],
        address=data[2],
        function_code=func,
        start_address=start_addr,
        data_length=data_len,
        data=data[8 : 8 + data_len],
        raw=data,
    )


def _parse_current_negative(data: bytes, offset: int) -> tuple[float, int]:
    """Parse a 2-byte current value with sign and decimal flag.

    Bit 7 of byte 0: sign (1 = negative)
    Bit 6 of byte 0: decimal flag (1 = divide by 10)
    Bits 5-0 of byte 0 + byte 1: raw magnitude

    Returns ``(current_amps, new_offset)``.
    """
    b0 = data[offset]
    b1 = data[offset + 1]
    is_negative = (b0 & 0x80) != 0
    has_decimal = (b0 & 0x40) != 0
    raw = b1 | ((b0 & 0x3F) << 8)
    current = raw / 10.0 if has_decimal else float(raw)
    if is_negative:
        current = -current
    return current, offset + 2


def parse_analog_quantity(data: bytes) -> AnalogQuantity | None:
    """Parse an Analog Quantity response payload (DP 140).

    Args:
        data: The DATA portion of the frame (after header, before CRC).

    Returns:
        Parsed :class:`AnalogQuantity` or ``None`` on parse failure.
    """
    try:
        aq = AnalogQuantity()
        off = 0

        aq.cell_count = data[off]; off += 1
        for _ in range(aq.cell_count):
            v = struct.unpack(">H", data[off:off + 2])[0]
            aq.cell_voltages.append(v / 1000.0)
            off += 2

        aq.temperature_count = data[off]; off += 1

        t = struct.unpack(">H", data[off:off + 2])[0]
        aq.mos_temperature = (t - 2730) / 10.0
        off += 2

        t = struct.unpack(">H", data[off:off + 2])[0]
        aq.pcb_temperature = (t - 2730) / 10.0
        off += 2

        for _ in range(aq.temperature_count - 2):
            t = struct.unpack(">H", data[off:off + 2])[0]
            aq.cell_temperatures.append((t - 2730) / 10.0)
            off += 2

        aq.current, off = _parse_current_negative(data, off)

        v = struct.unpack(">H", data[off:off + 2])[0]
        aq.module_voltage = v / 100.0
        off += 2

        v = struct.unpack(">H", data[off:off + 2])[0]
        aq.remaining_capacity = v / 10.0
        off += 2

        v = struct.unpack(">H", data[off:off + 2])[0]
        aq.total_capacity = v / 10.0
        off += 2

        aq.cycle_number = struct.unpack(">H", data[off:off + 2])[0]
        off += 2

        v = struct.unpack(">H", data[off:off + 2])[0]
        aq.design_capacity = v / 10.0
        off += 2

        aq.soc = struct.unpack(">H", data[off:off + 2])[0]
        off += 2

        # New version extension
        if len(data) - off >= 18:
            aq.soh = struct.unpack(">H", data[off:off + 2])[0]
            off += 2
            v = struct.unpack(">I", data[off:off + 4])[0]
            aq.cumulative_capacity = v / 10.0
            off += 4
            aq.remaining_time_min = struct.unpack(">i", data[off:off + 4])[0]
            off += 4
            off += 6  # 3 reserved uint16s
            aq.balance_current, off = _parse_current_negative(data, off)

        return aq
    except Exception:
        logger.exception("Failed to parse analog quantity")
        return None


def parse_product_info(data: bytes) -> ProductInfo | None:
    """Parse a Product Info response payload (DP 146).

    Expects exactly 60 bytes: 3 x 20-byte ASCII strings
    (firmware version, manufacturer, serial number).
    """
    if len(data) != 60:
        logger.warning("Product info expected 60 bytes, got %d", len(data))
        return None
    try:
        fw = data[0:20].decode("ascii", errors="replace").rstrip("\x00").strip()
        mfr = data[20:40].decode("ascii", errors="replace").rstrip("\x00").strip()
        sn = data[40:60].decode("ascii", errors="replace").rstrip("\x00").strip()
        return ProductInfo(firmware_version=fw, manufacturer_name=mfr, serial_number=sn)
    except Exception:
        logger.exception("Failed to parse product info")
        return None


def parse_warning_info(data: bytes) -> WarningInfo | None:
    """Parse a Warning Info response payload (DP 141).

    Contains cell states, temperature states, protection/fault/warning
    status registers, and per-cell balance flags.
    """
    try:
        wi = WarningInfo()
        off = 0

        wi.cell_count = data[off]; off += 1
        for _ in range(wi.cell_count):
            wi.cell_states.append(data[off]); off += 1

        wi.temperature_count = data[off]; off += 1
        wi.mos_temperature_state = data[off]; off += 1
        wi.pcb_temperature_state = data[off]; off += 1
        for _ in range(wi.temperature_count - 2):
            wi.cell_temperature_states.append(data[off]); off += 1

        wi.charge_current_state = data[off]; off += 1
        wi.voltage_state = data[off]; off += 1
        wi.discharge_current_state = data[off]; off += 1
        wi.battery_mode = data[off]; off += 1
        wi.status_register_1 = data[off]; off += 1
        wi.status_register_2 = data[off]; off += 1
        wi.status_register_3 = data[off]; off += 1
        off += 1  # reserved
        wi.status_register_5 = data[off]; off += 1
        off += 2  # 2 reserved bytes
        wi.warning_register_1 = data[off]; off += 1
        wi.warning_register_2 = data[off]; off += 1

        # Balance states: ceil(cell_count / 8) bytes, bitfield
        n_bytes = (wi.cell_count + 7) // 8
        for i in range(n_bytes):
            byte_val = data[off]; off += 1
            for bit in range(8):
                cell_idx = i * 8 + bit
                if cell_idx < wi.cell_count:
                    wi.balance_states.append(bool(byte_val & (1 << bit)))

        return wi
    except Exception:
        logger.exception("Failed to parse warning info")
        return None


def format_hex(data: bytes) -> str:
    """Format bytes as a space-separated hex string."""
    return " ".join(f"{b:02X}" for b in data)
