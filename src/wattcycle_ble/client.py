"""Async BLE client for Wattcycle battery monitors."""

from __future__ import annotations

import asyncio
import logging

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from .models import AnalogQuantity, ProductInfo, WarningInfo, WattFrame
from .protocol import (
    AUTH_KEY,
    AUTH_UUID,
    DEVICE_NAME_PREFIXES,
    DP_ANALOG_QUANTITY,
    DP_PRODUCT_INFO,
    DP_WARNING_INFO,
    FRAME_HEAD,
    FRAME_HEAD_ALT,
    FRAME_TAIL,
    MIN_FRAME_SIZE,
    NOTIFY_UUID,
    SERVICE_UUID,
    WRITE_UUID,
    build_read_frame,
    expected_response_length,
    format_hex,
    parse_analog_quantity,
    parse_frame,
    parse_product_info,
    parse_warning_info,
)

logger = logging.getLogger(__name__)


class WattcycleClient:
    """Async BLE client for XDZN/Wattcycle battery monitors.

    Supports use as an async context manager::

        async with WattcycleClient("C0:D6:3C:57:EF:2F") as client:
            data = await client.read_analog_quantity()
            print(data.soc)

    Args:
        address: BLE MAC address or ``BLEDevice`` to connect to.
    """

    def __init__(self, address: str | BLEDevice):
        self._address = address
        self._client: BleakClient | None = None
        self._response_buffer = bytearray()
        self._response_event = asyncio.Event()
        self._expected_len: int | None = None
        self.frame_head: int = FRAME_HEAD

    async def __aenter__(self) -> WattcycleClient:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.disconnect()

    @staticmethod
    async def scan(timeout: float = 10.0) -> list[BLEDevice]:
        """Scan for Wattcycle/XDZN devices.

        Args:
            timeout: Scan duration in seconds.

        Returns:
            List of discovered BLE devices with matching name prefixes.
        """
        logger.info("Scanning for %s devices (%.0fs)...", DEVICE_NAME_PREFIXES, timeout)
        devices = await BleakScanner.discover(timeout=timeout)
        matches = [
            d for d in devices
            if d.name and any(d.name.startswith(p) for p in DEVICE_NAME_PREFIXES)
        ]
        for d in matches:
            logger.info("Found: %s (%s)", d.name, d.address)
        return matches

    def _notification_handler(self, _sender: object, data: bytearray) -> None:
        """Handle incoming BLE notifications (packet reassembly)."""
        self._response_buffer.extend(data)

        if self._expected_len is None and len(self._response_buffer) >= 8:
            self._expected_len = expected_response_length(bytes(self._response_buffer))

        if self._expected_len and len(self._response_buffer) >= self._expected_len:
            self._response_event.set()

    async def connect(self) -> None:
        """Connect to the device, enable notifications, and authenticate."""
        logger.info("Connecting to %s...", self._address)
        self._client = BleakClient(self._address)
        await self._client.connect()
        logger.info("Connected")

        await self._client.start_notify(NOTIFY_UUID, self._notification_handler)
        logger.debug("Notifications enabled on FFF1")

        await self._client.write_gatt_char(AUTH_UUID, AUTH_KEY, response=False)
        logger.debug("Auth key sent")
        await asyncio.sleep(0.5)

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        if self._client and self._client.is_connected:
            try:
                await self._client.stop_notify(NOTIFY_UUID)
            except Exception:
                pass
            await self._client.disconnect()
            logger.info("Disconnected")

    @property
    def is_connected(self) -> bool:
        """Whether the BLE connection is active."""
        return self._client is not None and self._client.is_connected

    async def send_command(self, cmd: bytes, timeout: float = 5.0) -> bytes | None:
        """Send a raw command and wait for the complete response.

        Args:
            cmd: Complete frame bytes to send.
            timeout: Response timeout in seconds.

        Returns:
            Complete response bytes, or ``None`` on timeout.
        """
        self._response_buffer.clear()
        self._response_event.clear()
        self._expected_len = None

        logger.debug("TX: %s", format_hex(cmd))
        await self._client.write_gatt_char(WRITE_UUID, cmd, response=False)

        try:
            await asyncio.wait_for(self._response_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            if self._response_buffer:
                logger.warning(
                    "Timeout with partial data (%d bytes)", len(self._response_buffer)
                )
            else:
                logger.warning("Timeout: no response")
            return None

        response = bytes(self._response_buffer)
        logger.debug("RX: %s", format_hex(response))
        return response

    async def detect_frame_head(self) -> bool:
        """Auto-detect the frame header byte (``0x7E`` or ``0x1E``).

        Sends a product info read with each header and uses whichever
        gets a valid response. Must be called after :meth:`connect`.

        Returns:
            ``True`` if a working frame header was found.
        """
        for head in [FRAME_HEAD, FRAME_HEAD_ALT]:
            cmd = build_read_frame(DP_PRODUCT_INFO, frame_head=head)
            logger.debug("Trying frame head 0x%02X...", head)
            resp = await self.send_command(cmd, timeout=3.0)
            if resp and len(resp) >= MIN_FRAME_SIZE and resp[-1] == FRAME_TAIL:
                self.frame_head = head
                logger.info("Frame head detected: 0x%02X", head)
                return True
        logger.error("Failed to detect frame head")
        return False

    async def read_analog_quantity(self) -> AnalogQuantity | None:
        """Read the main battery data (DP 140).

        Returns:
            Parsed :class:`AnalogQuantity` with cell voltages, temperatures,
            current, SOC, capacity, etc. ``None`` on failure.
        """
        cmd = build_read_frame(DP_ANALOG_QUANTITY, frame_head=self.frame_head)
        resp = await self.send_command(cmd)
        if not resp:
            return None
        frame = parse_frame(resp)
        if not frame:
            return None
        return parse_analog_quantity(frame.data)

    async def read_product_info(self) -> ProductInfo | None:
        """Read product information (DP 146).

        Returns:
            Parsed :class:`ProductInfo` with firmware version, manufacturer,
            and serial number. ``None`` on failure.
        """
        cmd = build_read_frame(DP_PRODUCT_INFO, frame_head=self.frame_head)
        resp = await self.send_command(cmd)
        if not resp:
            return None
        frame = parse_frame(resp)
        if not frame:
            return None
        return parse_product_info(frame.data)

    async def read_warning_info(self) -> WarningInfo | None:
        """Read warning and status information (DP 141).

        Returns:
            Parsed :class:`WarningInfo` with protection flags, faults,
            and balance states. ``None`` on failure.
        """
        cmd = build_read_frame(DP_WARNING_INFO, frame_head=self.frame_head)
        resp = await self.send_command(cmd)
        if not resp:
            return None
        frame = parse_frame(resp)
        if not frame:
            return None
        return parse_warning_info(frame.data)
