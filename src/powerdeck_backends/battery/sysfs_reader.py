"""Read-only Linux power-supply battery discovery."""

from __future__ import annotations

import os
from pathlib import Path

from powerdeck_backends.battery.charge_types import (
    mode_from_charge_type,
    parse_charge_types,
)
from powerdeck_core.models import (
    BatteryInfo,
    ChargeCapabilities,
    ChargeInterval,
    ChargeMode,
    ChargeState,
)

_DEFAULT_POWER_SUPPLY_ROOT = Path("/sys/class/power_supply")


def _read_text(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    return value or None


def _read_int(path: Path) -> int | None:
    text = _read_text(path)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _read_scaled(path: Path, divisor: float) -> float | None:
    value = _read_int(path)
    if value is None:
        return None
    return value / divisor


def _read_bool(path: Path) -> bool | None:
    value = _read_int(path)
    if value is None:
        return None
    if value == 0:
        return False
    if value == 1:
        return True
    return None


class SysfsBatteryReader:
    """Read battery information exposed by the Linux power-supply class."""

    def __init__(
        self,
        root: Path = _DEFAULT_POWER_SUPPLY_ROOT,
    ) -> None:
        self.root = root

    def _battery_paths(self) -> tuple[Path, ...]:
        try:
            return tuple(
                sorted(
                    (
                        path
                        for path in self.root.iterdir()
                        if path.is_dir()
                        and path.name.startswith("BAT")
                    ),
                    key=lambda path: path.name,
                )
            )
        except OSError:
            return ()

    def read_batteries(self) -> tuple[BatteryInfo, ...]:
        return tuple(
            self._read_battery(path)
            for path in self._battery_paths()
        )

    def _read_battery(self, path: Path) -> BatteryInfo:
        parsed = parse_charge_types(
            _read_text(path / "charge_types")
        )
        active_charge_type = (
            _read_text(path / "charge_type")
            or parsed.active_raw
        )

        return BatteryInfo(
            name=path.name,
            path=str(path),
            present=_read_bool(path / "present"),
            status=_read_text(path / "status"),
            capacity_percent=_read_int(path / "capacity"),
            capacity_level=_read_text(path / "capacity_level"),
            technology=_read_text(path / "technology"),
            manufacturer=_read_text(path / "manufacturer"),
            model_name=_read_text(path / "model_name"),
            serial_number=_read_text(path / "serial_number"),
            cycle_count=_read_int(path / "cycle_count"),
            energy_now_wh=_read_scaled(
                path / "energy_now",
                1_000_000.0,
            ),
            energy_full_wh=_read_scaled(
                path / "energy_full",
                1_000_000.0,
            ),
            energy_full_design_wh=_read_scaled(
                path / "energy_full_design",
                1_000_000.0,
            ),
            charge_now_ah=_read_scaled(
                path / "charge_now",
                1_000_000.0,
            ),
            charge_full_ah=_read_scaled(
                path / "charge_full",
                1_000_000.0,
            ),
            charge_full_design_ah=_read_scaled(
                path / "charge_full_design",
                1_000_000.0,
            ),
            power_now_w=_read_scaled(
                path / "power_now",
                1_000_000.0,
            ),
            current_now_a=_read_scaled(
                path / "current_now",
                1_000_000.0,
            ),
            voltage_now_v=_read_scaled(
                path / "voltage_now",
                1_000_000.0,
            ),
            temperature_celsius=_read_scaled(
                path / "temp",
                10.0,
            ),
            charge_types=parsed.choices,
            active_charge_type=active_charge_type,
            charge_control_start_percent=_read_int(
                path / "charge_control_start_threshold"
            ),
            charge_control_end_percent=_read_int(
                path / "charge_control_end_threshold"
            ),
        )

    def read_charge_capabilities(self) -> ChargeCapabilities:
        detected_modes: set[ChargeMode] = set()
        custom_thresholds = False
        writable = False
        battery_paths = self._battery_paths()

        for path in battery_paths:
            parsed = parse_charge_types(
                _read_text(path / "charge_types")
            )
            for value in (*parsed.choices, parsed.active_raw):
                mode = mode_from_charge_type(value)
                if mode is not None:
                    detected_modes.add(mode)

            start_path = (
                path / "charge_control_start_threshold"
            )
            end_path = (
                path / "charge_control_end_threshold"
            )
            if start_path.exists() and end_path.exists():
                custom_thresholds = True
                detected_modes.add(ChargeMode.CUSTOM)
                writable = writable or (
                    os.access(start_path, os.W_OK)
                    and os.access(end_path, os.W_OK)
                )

            for mode_path in (
                path / "charge_type",
                path / "charge_types",
            ):
                writable = writable or (
                    mode_path.exists()
                    and os.access(mode_path, os.W_OK)
                )

        supported_modes = tuple(
            mode
            for mode in ChargeMode
            if mode in detected_modes
        )
        return ChargeCapabilities(
            available=bool(
                supported_modes
                or custom_thresholds
            ),
            provider=(
                "kernel-power-supply"
                if battery_paths
                else None
            ),
            supported_modes=supported_modes,
            custom_thresholds=custom_thresholds,
            writable=writable,
        )

    def read_charge_state(self) -> ChargeState:
        batteries = self.read_batteries()
        if not batteries:
            return ChargeState(source="kernel-power-supply")

        battery = next(
            (
                candidate
                for candidate in batteries
                if candidate.active_charge_type is not None
                or candidate.charge_control_start_percent is not None
                or candidate.charge_control_end_percent is not None
            ),
            batteries[0],
        )

        interval: ChargeInterval | None = None
        if (
            battery.charge_control_start_percent is not None
            and battery.charge_control_end_percent is not None
        ):
            interval = ChargeInterval(
                start_percent=(
                    battery.charge_control_start_percent
                ),
                end_percent=(
                    battery.charge_control_end_percent
                ),
            )

        return ChargeState(
            battery_name=battery.name,
            mode=mode_from_charge_type(
                battery.active_charge_type
            ),
            interval=interval,
            source="kernel-power-supply",
        )


__all__ = ["SysfsBatteryReader"]
