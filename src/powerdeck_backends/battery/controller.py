"""Transactional battery charge control through Linux power-supply sysfs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from powerdeck_core.errors import (
    CommandExecutionError,
    MissingCapabilityError,
    PermissionDeniedError,
    RollbackError,
    StateVerificationError,
)
from powerdeck_core.models import ChargeInterval, ChargeMode, SerializableModel
from powerdeck_core.validation import (
    validate_charge_interval,
    validate_charge_mode,
)

_DEFAULT_ROOT = Path("/sys/class/power_supply")
type ReadText = Callable[[Path], str | None]
type WriteText = Callable[[Path, str], None]

_MODE_ALIASES: dict[ChargeMode, tuple[str, ...]] = {
    ChargeMode.ADAPTIVE: ("adaptive",),
    ChargeMode.STANDARD: ("standard", "normal"),
    ChargeMode.EXPRESS: ("express", "expresscharge", "fast"),
    ChargeMode.PRIMARILY_AC: (
        "primarilyac",
        "primarily_ac",
        "primarily-ac",
        "ac",
    ),
    ChargeMode.CUSTOM: ("custom",),
}


@dataclass(frozen=True, slots=True)
class ChargeControlStatus(SerializableModel):
    battery_name: str | None
    current_mode: ChargeMode | None
    available_modes: tuple[ChargeMode, ...]
    interval: ChargeInterval | None
    source: str | None
    battery_path: str | None


@dataclass(frozen=True, slots=True)
class ChargeApplyResult(SerializableModel):
    battery_name: str
    requested_mode: ChargeMode
    previous_mode: ChargeMode | None
    current_mode: ChargeMode
    previous_interval: ChargeInterval | None
    current_interval: ChargeInterval | None
    changed: bool
    verified: bool
    source: str


@dataclass(frozen=True, slots=True)
class _BatteryInterface:
    directory: Path

    @property
    def type_path(self) -> Path:
        return self.directory / "type"

    @property
    def mode_path(self) -> Path:
        return self.directory / "charge_type"

    @property
    def modes_path(self) -> Path:
        return self.directory / "charge_types"

    @property
    def start_path(self) -> Path:
        return self.directory / "charge_control_start_threshold"

    @property
    def end_path(self) -> Path:
        return self.directory / "charge_control_end_threshold"


def _read_text(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    return value or None


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def _normalized(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum() or character in "_-")


def _mode_from_raw(value: str | None) -> ChargeMode | None:
    if value is None:
        return None
    candidate = _normalized(value)
    for mode, aliases in _MODE_ALIASES.items():
        if any(_normalized(alias) == candidate for alias in aliases):
            return mode
    return None


def _raw_choices(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    cleaned = value.replace("[", " ").replace("]", " ").replace(",", " ")
    return tuple(token for token in cleaned.split() if token)


def _available_modes(choices: tuple[str, ...]) -> tuple[ChargeMode, ...]:
    modes: list[ChargeMode] = []
    for choice in choices:
        mode = _mode_from_raw(choice)
        if mode is not None and mode not in modes:
            modes.append(mode)
    return tuple(modes)


def _choice_for_mode(
    mode: ChargeMode,
    choices: tuple[str, ...],
) -> str | None:
    return next(
        (
            choice
            for choice in choices
            if _mode_from_raw(choice) is mode
        ),
        None,
    )


def _read_percent(read_text: ReadText, path: Path) -> int | None:
    value = read_text(path)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


class SysfsChargeController:
    """Apply Dell-compatible charge modes and thresholds safely."""

    def __init__(
        self,
        root: Path = _DEFAULT_ROOT,
        *,
        read_text: ReadText | None = None,
        write_text: WriteText | None = None,
    ) -> None:
        self.root = root
        self._read_text = read_text or _read_text
        self._write_text = write_text or _write_text

    def _interfaces(self) -> tuple[_BatteryInterface, ...]:
        try:
            directories = sorted(
                (path for path in self.root.iterdir() if path.is_dir()),
                key=lambda path: path.name,
            )
        except OSError:
            return ()

        interfaces: list[_BatteryInterface] = []
        for directory in directories:
            interface = _BatteryInterface(directory)
            supply_type = self._read_text(interface.type_path)
            if supply_type != "Battery":
                continue
            if (
                interface.mode_path.exists()
                or interface.start_path.exists()
                or interface.end_path.exists()
            ):
                interfaces.append(interface)
        return tuple(interfaces)

    def _require_interface(self) -> _BatteryInterface:
        interfaces = self._interfaces()
        if not interfaces:
            raise MissingCapabilityError(
                "No writable battery charge-control interface was found.",
                component="battery",
            )
        return interfaces[0]

    def _read_status(
        self,
        interface: _BatteryInterface,
    ) -> ChargeControlStatus:
        choices = _raw_choices(self._read_text(interface.modes_path))
        current = _mode_from_raw(self._read_text(interface.mode_path))
        available = _available_modes(choices)
        if current is not None and current not in available:
            available = (*available, current)

        start = _read_percent(self._read_text, interface.start_path)
        end = _read_percent(self._read_text, interface.end_path)
        interval = (
            ChargeInterval(start, end)
            if start is not None and end is not None
            else None
        )
        return ChargeControlStatus(
            battery_name=interface.directory.name,
            current_mode=current,
            available_modes=available,
            interval=interval,
            source="linux-power-supply-sysfs",
            battery_path=str(interface.directory),
        )

    def read_status(self) -> ChargeControlStatus:
        interfaces = self._interfaces()
        if not interfaces:
            return ChargeControlStatus(
                battery_name=None,
                current_mode=None,
                available_modes=(),
                interval=None,
                source=None,
                battery_path=None,
            )
        return self._read_status(interfaces[0])

    def _write(self, path: Path, value: str) -> None:
        try:
            self._write_text(path, f"{value}\n")
        except PermissionError as error:
            raise PermissionDeniedError(
                "Permission denied while changing battery charge control.",
                component="battery",
                details={"path": str(path), "value": value},
            ) from error
        except OSError as error:
            raise CommandExecutionError(
                "The kernel rejected a battery charge-control write.",
                component="battery",
                details={
                    "path": str(path),
                    "value": value,
                    "reason": str(error),
                },
            ) from error

    def _set_mode_raw(
        self,
        interface: _BatteryInterface,
        mode: ChargeMode,
    ) -> None:
        choices = _raw_choices(self._read_text(interface.modes_path))
        raw = _choice_for_mode(mode, choices)
        if raw is None:
            raise MissingCapabilityError(
                f"Charging mode is unavailable: {mode.value}",
                component="battery",
            )
        self._write(interface.mode_path, raw)

    def apply_mode(
        self,
        value: str | ChargeMode,
    ) -> ChargeApplyResult:
        interface = self._require_interface()
        before = self._read_status(interface)
        requested = validate_charge_mode(
            value,
            before.available_modes,
        )
        if before.current_mode is requested:
            return ChargeApplyResult(
                battery_name=interface.directory.name,
                requested_mode=requested,
                previous_mode=before.current_mode,
                current_mode=requested,
                previous_interval=before.interval,
                current_interval=before.interval,
                changed=False,
                verified=True,
                source="linux-power-supply-sysfs",
            )

        self._set_mode_raw(interface, requested)
        after = self._read_status(interface)
        if after.current_mode is requested:
            return ChargeApplyResult(
                battery_name=interface.directory.name,
                requested_mode=requested,
                previous_mode=before.current_mode,
                current_mode=requested,
                previous_interval=before.interval,
                current_interval=after.interval,
                changed=True,
                verified=True,
                source="linux-power-supply-sysfs",
            )

        if before.current_mode is not None:
            self._set_mode_raw(interface, before.current_mode)
        restored = self._read_status(interface)
        if restored.current_mode is not before.current_mode:
            raise RollbackError(
                "Battery mode verification failed and rollback failed.",
                component="battery",
            )
        raise StateVerificationError(
            "Battery mode verification failed; the previous mode was restored.",
            component="battery",
        )

    def _write_interval(
        self,
        interface: _BatteryInterface,
        interval: ChargeInterval,
        current: ChargeInterval,
    ) -> None:
        if interval.end_percent > current.end_percent:
            self._write(interface.end_path, str(interval.end_percent))
            self._write(interface.start_path, str(interval.start_percent))
        else:
            self._write(interface.start_path, str(interval.start_percent))
            self._write(interface.end_path, str(interval.end_percent))

    def apply_custom(
        self,
        start_percent: object,
        end_percent: object,
    ) -> ChargeApplyResult:
        interface = self._require_interface()
        before = self._read_status(interface)
        if before.interval is None:
            raise MissingCapabilityError(
                "Custom charging thresholds are unavailable.",
                component="battery",
            )
        requested_interval = validate_charge_interval(
            start_percent,
            end_percent,
        )
        validate_charge_mode(
            ChargeMode.CUSTOM,
            before.available_modes,
        )

        if before.current_mode is not ChargeMode.CUSTOM:
            self._set_mode_raw(interface, ChargeMode.CUSTOM)
        self._write_interval(
            interface,
            requested_interval,
            before.interval,
        )
        after = self._read_status(interface)
        if (
            after.current_mode is ChargeMode.CUSTOM
            and after.interval == requested_interval
        ):
            return ChargeApplyResult(
                battery_name=interface.directory.name,
                requested_mode=ChargeMode.CUSTOM,
                previous_mode=before.current_mode,
                current_mode=ChargeMode.CUSTOM,
                previous_interval=before.interval,
                current_interval=requested_interval,
                changed=(
                    before.current_mode is not ChargeMode.CUSTOM
                    or before.interval != requested_interval
                ),
                verified=True,
                source="linux-power-supply-sysfs",
            )

        self._write_interval(
            interface,
            before.interval,
            after.interval or requested_interval,
        )
        if before.current_mode is not None:
            self._set_mode_raw(interface, before.current_mode)
        restored = self._read_status(interface)
        if (
            restored.current_mode is not before.current_mode
            or restored.interval != before.interval
        ):
            raise RollbackError(
                "Custom charging verification failed and rollback failed.",
                component="battery",
            )
        raise StateVerificationError(
            "Custom charging verification failed; previous settings were restored.",
            component="battery",
        )


__all__ = [
    "ChargeApplyResult",
    "ChargeControlStatus",
    "SysfsChargeController",
]
