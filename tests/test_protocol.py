"""Tests for the wattcycle_ble protocol module.

Uses real captured data from a Wattcycle XDZN device to validate
CRC calculation, frame building, and response parsing.
"""

from wattcycle_ble.protocol import (
    DP_ANALOG_QUANTITY,
    DP_PRODUCT_INFO,
    DP_WARNING_INFO,
    build_read_frame,
    modbus_crc16,
    parse_analog_quantity,
    parse_frame,
    parse_product_info,
    parse_warning_info,
    verify_crc,
    _parse_current_negative,
)


# Real captured response: Warning Info from XDZN_001_EF2F
SAMPLE_WARNING_RESPONSE = bytes([
    0x7E, 0x00, 0x01, 0x03, 0x00, 0x8D, 0x00, 0x18,
    0x04, 0x00, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x06, 0x01, 0x00, 0x00, 0x18, 0x00, 0x00, 0x00,
    0x1F, 0x91, 0x0D,
])

# Real captured response: Analog Quantity from XDZN_001_EF2F
SAMPLE_ANALOG_RESPONSE = bytes([
    0x7E, 0x00, 0x01, 0x03, 0x00, 0x8C, 0x00, 0x20,
    0x04, 0x0C, 0xDE, 0x0C, 0xDD, 0x0C, 0xDF, 0x0C,
    0xDA, 0x04, 0x0B, 0x65, 0x0B, 0x70, 0x0B, 0x5A,
    0x0B, 0x5A, 0x40, 0x00, 0x05, 0x25, 0x07, 0x2A,
    0x0C, 0x44, 0x00, 0x05, 0x0C, 0x44, 0x00, 0x3A,
    0x4B, 0x22, 0x0D,
])

# Real captured response: Product Info from XDZN_001_EF2F
SAMPLE_PRODUCT_RESPONSE = bytes([
    0x7E, 0x00, 0x01, 0x03, 0x00, 0x92, 0x00, 0x3C,
    0x57, 0x54, 0x31, 0x32, 0x5F, 0x32, 0x30, 0x30,
    0x30, 0x34, 0x53, 0x57, 0x31, 0x30, 0x5F, 0x4C,
    0x34, 0x34, 0x37, 0x00, 0x20, 0x20, 0x20, 0x20,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x36, 0x30, 0x30, 0x31, 0x36, 0x30, 0x31, 0x36,
    0x32, 0x30, 0x37, 0x32, 0x37, 0x30, 0x30, 0x30,
    0x31, 0x00, 0x00, 0x00,
    0x52, 0xAA, 0x0D,
])


class TestModbusCRC:
    def test_known_crc(self):
        """CRC of the warning response payload matches captured value."""
        payload = SAMPLE_WARNING_RESPONSE[:-3]
        assert modbus_crc16(payload) == 0x1F91

    def test_analog_crc(self):
        payload = SAMPLE_ANALOG_RESPONSE[:-3]
        expected = (SAMPLE_ANALOG_RESPONSE[-3] << 8) | SAMPLE_ANALOG_RESPONSE[-2]
        assert modbus_crc16(payload) == expected

    def test_product_crc(self):
        payload = SAMPLE_PRODUCT_RESPONSE[:-3]
        expected = (SAMPLE_PRODUCT_RESPONSE[-3] << 8) | SAMPLE_PRODUCT_RESPONSE[-2]
        assert modbus_crc16(payload) == expected

    def test_empty(self):
        """CRC of empty data should not raise."""
        result = modbus_crc16(b"")
        assert isinstance(result, int)


class TestBuildReadFrame:
    def test_analog_quantity_frame(self):
        frame = build_read_frame(DP_ANALOG_QUANTITY)
        assert frame[0] == 0x7E  # head
        assert frame[1] == 0x00  # version
        assert frame[2] == 0x01  # device addr
        assert frame[3] == 0x03  # func read
        assert frame[4:6] == b"\x00\x8C"  # address 140
        assert frame[6:8] == b"\x00\x00"  # read count
        assert frame[-1] == 0x0D  # tail
        assert len(frame) == 11

    def test_warning_info_frame(self):
        frame = build_read_frame(DP_WARNING_INFO)
        assert frame[4:6] == b"\x00\x8D"

    def test_product_info_frame(self):
        frame = build_read_frame(DP_PRODUCT_INFO)
        assert frame[4:6] == b"\x00\x92"

    def test_alt_frame_head(self):
        frame = build_read_frame(DP_ANALOG_QUANTITY, frame_head=0x1E)
        assert frame[0] == 0x1E
        assert frame[-1] == 0x0D

    def test_crc_valid(self):
        """Built frames should have valid CRC."""
        frame = build_read_frame(DP_ANALOG_QUANTITY)
        assert verify_crc(frame)


class TestVerifyCRC:
    def test_valid_warning(self):
        assert verify_crc(SAMPLE_WARNING_RESPONSE)

    def test_valid_analog(self):
        assert verify_crc(SAMPLE_ANALOG_RESPONSE)

    def test_valid_product(self):
        assert verify_crc(SAMPLE_PRODUCT_RESPONSE)

    def test_corrupted(self):
        bad = bytearray(SAMPLE_WARNING_RESPONSE)
        bad[10] ^= 0xFF  # corrupt a data byte
        assert not verify_crc(bytes(bad))

    def test_too_short(self):
        assert not verify_crc(b"\x7E\x00\x01")


class TestParseFrame:
    def test_warning_frame(self):
        frame = parse_frame(SAMPLE_WARNING_RESPONSE)
        assert frame is not None
        assert frame.version == 0
        assert frame.address == 1
        assert frame.function_code == 0x03
        assert frame.start_address == 0x8D
        assert frame.data_length == 24
        assert len(frame.data) == 24

    def test_analog_frame(self):
        frame = parse_frame(SAMPLE_ANALOG_RESPONSE)
        assert frame is not None
        assert frame.start_address == 0x8C
        assert frame.data_length == 0x20  # 32

    def test_product_frame(self):
        frame = parse_frame(SAMPLE_PRODUCT_RESPONSE)
        assert frame is not None
        assert frame.start_address == 0x92
        assert frame.data_length == 60

    def test_error_response(self):
        """Function code 0x86 should return None."""
        bad = bytearray(SAMPLE_WARNING_RESPONSE)
        bad[3] = 0x86
        assert parse_frame(bytes(bad)) is None

    def test_too_short(self):
        assert parse_frame(b"\x7E\x00") is None

    def test_bad_head(self):
        bad = bytearray(SAMPLE_WARNING_RESPONSE)
        bad[0] = 0xFF
        assert parse_frame(bytes(bad)) is None

    def test_bad_tail(self):
        bad = bytearray(SAMPLE_WARNING_RESPONSE)
        bad[-1] = 0xFF
        assert parse_frame(bytes(bad)) is None


class TestParseCurrentNegative:
    def test_zero(self):
        current, off = _parse_current_negative(b"\x00\x00", 0)
        assert current == 0.0
        assert off == 2

    def test_positive_with_decimal(self):
        # 0x40 = has_decimal, 0x00 in high bits, value = 0x00 | (0x00 << 8) = 0
        # Let's use 0x40 0x64 -> has_decimal, raw = 100, current = 10.0
        current, _ = _parse_current_negative(b"\x40\x64", 0)
        assert current == 10.0

    def test_negative_with_decimal(self):
        # 0xC0 = negative + decimal, 0x64 = 100, raw = 100, current = -10.0
        current, _ = _parse_current_negative(b"\xC0\x64", 0)
        assert current == -10.0

    def test_positive_no_decimal(self):
        # 0x00 0x0A -> raw = 10, no decimal, current = 10.0
        current, _ = _parse_current_negative(b"\x00\x0A", 0)
        assert current == 10.0

    def test_negative_no_decimal(self):
        # 0x80 0x0A -> negative, raw = 10, current = -10.0
        current, _ = _parse_current_negative(b"\x80\x0A", 0)
        assert current == -10.0

    def test_large_value(self):
        # 0x43 0xFF -> has_decimal, raw = 0xFF | (0x03 << 8) = 1023, current = 102.3
        current, _ = _parse_current_negative(b"\x43\xFF", 0)
        assert abs(current - 102.3) < 0.01

    def test_sample_data(self):
        """The captured analog response has current bytes 0x40 0x00 -> 0.0A."""
        current, _ = _parse_current_negative(b"\x40\x00", 0)
        assert current == 0.0


class TestParseAnalogQuantity:
    def test_real_data(self):
        frame = parse_frame(SAMPLE_ANALOG_RESPONSE)
        assert frame is not None
        aq = parse_analog_quantity(frame.data)
        assert aq is not None

        assert aq.cell_count == 4
        assert len(aq.cell_voltages) == 4
        assert abs(aq.cell_voltages[0] - 3.294) < 0.001
        assert abs(aq.cell_voltages[1] - 3.293) < 0.001
        assert abs(aq.cell_voltages[2] - 3.295) < 0.001
        assert abs(aq.cell_voltages[3] - 3.290) < 0.001

        assert aq.temperature_count == 4
        assert abs(aq.mos_temperature - 18.7) < 0.1
        assert abs(aq.pcb_temperature - 19.8) < 0.1
        assert len(aq.cell_temperatures) == 2
        assert abs(aq.cell_temperatures[0] - 17.6) < 0.1
        assert abs(aq.cell_temperatures[1] - 17.6) < 0.1

        assert aq.current == 0.0
        assert abs(aq.module_voltage - 13.17) < 0.01
        assert abs(aq.remaining_capacity - 183.4) < 0.1
        assert abs(aq.total_capacity - 314.0) < 0.1
        assert aq.cycle_number == 5
        assert abs(aq.design_capacity - 314.0) < 0.1
        assert aq.soc == 58

    def test_empty_data(self):
        assert parse_analog_quantity(b"") is None

    def test_truncated(self):
        assert parse_analog_quantity(b"\x04") is None


class TestParseProductInfo:
    def test_real_data(self):
        frame = parse_frame(SAMPLE_PRODUCT_RESPONSE)
        assert frame is not None
        pi = parse_product_info(frame.data)
        assert pi is not None
        assert pi.firmware_version == "WT12_20004SW10_L447"
        assert pi.serial_number == "60016016207270001"

    def test_wrong_length(self):
        assert parse_product_info(b"\x00" * 30) is None


class TestParseWarningInfo:
    def test_real_data(self):
        frame = parse_frame(SAMPLE_WARNING_RESPONSE)
        assert frame is not None
        wi = parse_warning_info(frame.data)
        assert wi is not None
        assert wi.cell_count == 4
        assert len(wi.cell_states) == 4
        assert wi.temperature_count == 4
        assert wi.protections == []
        assert wi.faults == []
        assert wi.warnings == []

    def test_empty_data(self):
        assert parse_warning_info(b"") is None
