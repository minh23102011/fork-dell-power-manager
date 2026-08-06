"""Read-only PowerDeck command-line interface."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Protocol, TextIO

from powerdeck_backends.scanner import DiscoverySnapshot, PowerDeckScanner
from powerdeck_core import __version__
from powerdeck_core.models import Severity


class SnapshotScanner(Protocol):
    def scan(self) -> DiscoverySnapshot: ...


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="powerdeckctl",
        description="Inspect PowerDeck hardware capabilities and current state.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)
    status_parser = subparsers.add_parser(
        "status",
        help="Scan the current system without performing hardware writes.",
    )
    status_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the complete snapshot as JSON.",
    )
    status_parser.add_argument(
        "--compact",
        action="store_true",
        help="Emit compact JSON; requires --json.",
    )
    return parser


def _format_unknown(value: object | None) -> str:
    return "unknown" if value is None else str(value)


def _format_human(snapshot: DiscoverySnapshot) -> str:
    status = snapshot.status
    capabilities = snapshot.capabilities
    machine = status.machine

    machine_name = " ".join(
        part for part in (machine.vendor, machine.product_name) if part
    ) or "unknown"
    lines = [
        "PowerDeck status",
        f"Machine: {machine_name}",
        f"OS: {_format_unknown(machine.os_name)}",
        f"Kernel: {_format_unknown(machine.kernel_release)}",
    ]

    if status.batteries:
        for battery in status.batteries:
            health = battery.health_percent
            health_text = "unknown" if health is None else f"{health:.1f}%"
            capacity_text = (
                "unknown"
                if battery.capacity_percent is None
                else f"{battery.capacity_percent}%"
            )
            lines.append(
                f"Battery {battery.name}: {capacity_text}, "
                f"{_format_unknown(battery.status)}, health {health_text}"
            )
    else:
        lines.append("Battery: not detected")

    charge_mode = (
        status.charge.mode.value if status.charge.mode is not None else "unknown"
    )
    interval = status.charge.interval
    interval_text = (
        "unknown"
        if interval is None
        else f"{interval.start_percent}% -> {interval.end_percent}%"
    )
    lines.append(f"Charging: {charge_mode}, interval {interval_text}")

    thermal_profile = (
        status.thermal.current_profile.value
        if status.thermal.current_profile is not None
        else "unknown"
    )
    lines.append(f"Thermal profile: {thermal_profile}")

    cpu = capabilities.cpu
    lines.append(
        "CPU: "
        f"{_format_unknown(cpu.model_name)}, "
        f"driver {_format_unknown(cpu.scaling_driver)}, "
        f"governor {_format_unknown(cpu.current_governor)}"
    )

    on_ac = status.on_ac_power
    ac_text = "unknown" if on_ac is None else ("online" if on_ac else "offline")
    lines.append(f"AC power: {ac_text}")

    manager = status.power_manager.provider or "none/ambiguous"
    lines.append(f"Power manager: {manager}")

    errors = sum(issue.severity is Severity.ERROR for issue in status.diagnostics)
    warnings = sum(issue.severity is Severity.WARNING for issue in status.diagnostics)
    info = sum(issue.severity is Severity.INFO for issue in status.diagnostics)
    lines.append(f"Diagnostics: {errors} error, {warnings} warning, {info} info")
    for issue in status.diagnostics:
        lines.append(f"  [{issue.severity.value}] {issue.code}: {issue.message}")
    return "\n".join(lines)


def run(
    argv: Sequence[str] | None = None,
    *,
    scanner: SnapshotScanner | None = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "status":
        parser.error(f"unsupported command: {args.command}")

    if args.compact and not args.json:
        print("powerdeckctl: --compact requires --json", file=stderr)
        return 2

    active_scanner = scanner if scanner is not None else PowerDeckScanner()
    snapshot = active_scanner.scan()
    if args.json:
        print(snapshot.to_json(indent=None if args.compact else 2), file=stdout)
    else:
        print(_format_human(snapshot), file=stdout)
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
