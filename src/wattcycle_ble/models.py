"""Data models for Wattcycle BLE protocol responses."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WattFrame:
    """Parsed response frame."""

    version: int
    address: int
    function_code: int
    start_address: int
    data_length: int
    data: bytes
    raw: bytes


@dataclass
class AnalogQuantity:
    """Battery analog data (DP 140 / 0x8C).

    Contains cell voltages, temperatures, current, capacity, and SOC.
    """

    cell_count: int = 0
    cell_voltages: list[float] = field(default_factory=list)
    temperature_count: int = 0
    mos_temperature: float = 0.0
    pcb_temperature: float = 0.0
    cell_temperatures: list[float] = field(default_factory=list)
    current: float = 0.0
    module_voltage: float = 0.0
    remaining_capacity: float = 0.0
    total_capacity: float = 0.0
    cycle_number: int = 0
    design_capacity: float = 0.0
    soc: int = 0
    # New version fields (None if device uses old protocol)
    soh: int | None = None
    cumulative_capacity: float | None = None
    remaining_time_min: int | None = None
    balance_current: float | None = None


@dataclass
class ProductInfo:
    """Product information (DP 146 / 0x92)."""

    firmware_version: str = ""
    manufacturer_name: str = ""
    serial_number: str = ""


@dataclass
class WarningInfo:
    """Warning and status information (DP 141 / 0x8D).

    Cell states, temperature states, protection flags, and fault flags.
    """

    cell_count: int = 0
    cell_states: list[int] = field(default_factory=list)
    temperature_count: int = 0
    mos_temperature_state: int = 0
    pcb_temperature_state: int = 0
    cell_temperature_states: list[int] = field(default_factory=list)
    charge_current_state: int = 0
    voltage_state: int = 0
    discharge_current_state: int = 0
    battery_mode: int = 0
    status_register_1: int = 0
    status_register_2: int = 0
    status_register_3: int = 0
    status_register_5: int = 0
    warning_register_1: int = 0
    warning_register_2: int = 0
    balance_states: list[bool] = field(default_factory=list)

    @property
    def protections(self) -> list[str]:
        """Active protection flags as human-readable strings."""
        flags = []
        r1 = self.status_register_1
        if r1 & 0x01:
            flags.append("cell_overcharge")
        if r1 & 0x02:
            flags.append("cell_overdischarge")
        if r1 & 0x04:
            flags.append("total_overcharge")
        if r1 & 0x08:
            flags.append("total_overdischarge")
        if r1 & 0x10:
            flags.append("charge_overcurrent")
        if r1 & 0x20:
            flags.append("discharge_overcurrent")
        if r1 & 0x40:
            flags.append("hardware")
        if r1 & 0x80:
            flags.append("charge_voltage_high")
        r2 = self.status_register_2
        if r2 & 0x01:
            flags.append("charge_high_temp")
        if r2 & 0x02:
            flags.append("discharge_high_temp")
        if r2 & 0x04:
            flags.append("charge_low_temp")
        if r2 & 0x08:
            flags.append("discharge_low_temp")
        if r2 & 0x10:
            flags.append("mos_high_temp")
        if r2 & 0x20:
            flags.append("env_high_temp")
        if r2 & 0x40:
            flags.append("env_low_temp")
        return flags

    @property
    def faults(self) -> list[str]:
        """Active fault flags as human-readable strings."""
        flags = []
        r5 = self.status_register_5
        if r5 & 0x01:
            flags.append("cell")
        if r5 & 0x02:
            flags.append("charge_mos")
        if r5 & 0x04:
            flags.append("discharge_mos")
        if r5 & 0x08:
            flags.append("temperature")
        return flags

    @property
    def warnings(self) -> list[str]:
        """Active warning flags as human-readable strings."""
        flags = []
        w1 = self.warning_register_1
        if w1 & 0x01:
            flags.append("cell_overcharge")
        if w1 & 0x02:
            flags.append("cell_overdischarge")
        if w1 & 0x04:
            flags.append("total_overcharge")
        if w1 & 0x08:
            flags.append("total_overdischarge")
        if w1 & 0x10:
            flags.append("charge_overcurrent")
        if w1 & 0x20:
            flags.append("discharge_overcurrent")
        if w1 & 0x40:
            flags.append("hardware")
        if w1 & 0x80:
            flags.append("charge_voltage_high")
        w2 = self.warning_register_2
        if w2 & 0x01:
            flags.append("charge_high_temp")
        if w2 & 0x02:
            flags.append("discharge_high_temp")
        if w2 & 0x04:
            flags.append("charge_low_temp")
        if w2 & 0x08:
            flags.append("discharge_low_temp")
        if w2 & 0x10:
            flags.append("env_high_temp")
        if w2 & 0x20:
            flags.append("env_low_temp")
        if w2 & 0x40:
            flags.append("mos_high_temp")
        return flags
