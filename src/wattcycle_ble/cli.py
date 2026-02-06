"""Command-line interface for wattcycle-ble."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .client import WattcycleClient
from .models import AnalogQuantity


def print_battery_data(aq: AnalogQuantity) -> None:
    """Pretty-print battery data to stdout."""
    print()
    print("=" * 60)
    print("  BATTERY STATUS")
    print("=" * 60)

    print(f"\n  SOC:                {aq.soc}%")
    print(f"  Current:            {aq.current:.1f} A")
    print(f"  Module Voltage:     {aq.module_voltage:.2f} V")
    print(f"  Remaining Capacity: {aq.remaining_capacity:.1f} Ah")
    print(f"  Total Capacity:     {aq.total_capacity:.1f} Ah")
    print(f"  Design Capacity:    {aq.design_capacity:.1f} Ah")
    print(f"  Cycle Count:        {aq.cycle_number}")

    print(f"\n  Cell Voltages ({aq.cell_count} cells):")
    for i, v in enumerate(aq.cell_voltages):
        print(f"    Cell {i + 1:2d}: {v:.3f} V")
    if aq.cell_voltages:
        vmin = min(aq.cell_voltages)
        vmax = max(aq.cell_voltages)
        print(f"    Delta:  {(vmax - vmin) * 1000:.1f} mV  (min={vmin:.3f}, max={vmax:.3f})")

    print(f"\n  Temperatures ({aq.temperature_count} sensors):")
    print(f"    MOS:    {aq.mos_temperature:.1f} C")
    print(f"    PCB:    {aq.pcb_temperature:.1f} C")
    for i, t in enumerate(aq.cell_temperatures):
        print(f"    Cell {i + 1}: {t:.1f} C")

    if aq.soh is not None:
        print(f"\n  SOH:                {aq.soh}%")
    if aq.cumulative_capacity is not None:
        print(f"  Cumulative Cap:     {aq.cumulative_capacity:.1f} Ah")
    if aq.remaining_time_min is not None:
        hours = aq.remaining_time_min // 60
        mins = aq.remaining_time_min % 60
        print(f"  Remaining Time:     {hours}h {mins}m")
    if aq.balance_current is not None:
        print(f"  Balance Current:    {aq.balance_current:.1f} A")

    print()


async def cmd_scan(args: argparse.Namespace) -> None:
    """Scan for Wattcycle devices."""
    devices = await WattcycleClient.scan(timeout=args.timeout)
    if not devices:
        print("No Wattcycle/XDZN devices found.")
        return
    print(f"\nFound {len(devices)} device(s):")
    for d in devices:
        print(f"  {d.name}  ({d.address})")


async def cmd_read(args: argparse.Namespace) -> None:
    """Connect and read battery data."""
    async with WattcycleClient(args.mac) as client:
        if not await client.detect_frame_head():
            print("Could not communicate with device.", file=sys.stderr)
            sys.exit(1)

        # Product info
        pi = await client.read_product_info()
        if pi:
            print(f"\n  Firmware:     {pi.firmware_version}")
            print(f"  Manufacturer: {pi.manufacturer_name}")
            print(f"  Serial:       {pi.serial_number}")

        # Battery data
        aq = await client.read_analog_quantity()
        if aq:
            print_battery_data(aq)

        # Warnings
        wi = await client.read_warning_info()
        if wi:
            if wi.protections:
                print(f"  Protections:  {', '.join(wi.protections)}")
            if wi.faults:
                print(f"  Faults:       {', '.join(wi.faults)}")
            if wi.warnings:
                print(f"  Warnings:     {', '.join(wi.warnings)}")
            if not (wi.protections or wi.faults or wi.warnings):
                print("  No active warnings or faults.")


async def cmd_loop(args: argparse.Namespace) -> None:
    """Continuously poll battery data."""
    async with WattcycleClient(args.mac) as client:
        if not await client.detect_frame_head():
            print("Could not communicate with device.", file=sys.stderr)
            sys.exit(1)

        try:
            while True:
                aq = await client.read_analog_quantity()
                if aq:
                    print_battery_data(aq)
                await asyncio.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nStopped.")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="wattcycle-ble",
        description="BLE client for XDZN/Wattcycle battery monitors",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="enable debug logging",
    )

    sub = parser.add_subparsers(dest="command")

    # scan
    scan_p = sub.add_parser("scan", help="scan for Wattcycle devices")
    scan_p.add_argument(
        "-t", "--timeout", type=float, default=10.0,
        help="scan timeout in seconds (default: 10)",
    )

    # read
    read_p = sub.add_parser("read", help="read battery data (default)")
    read_p.add_argument("mac", help="device MAC address")

    # loop
    loop_p = sub.add_parser("loop", help="continuously poll battery data")
    loop_p.add_argument("mac", help="device MAC address")
    loop_p.add_argument(
        "-i", "--interval", type=float, default=5.0,
        help="poll interval in seconds (default: 5)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.command == "scan":
        asyncio.run(cmd_scan(args))
    elif args.command == "loop":
        asyncio.run(cmd_loop(args))
    elif args.command == "read":
        asyncio.run(cmd_read(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
