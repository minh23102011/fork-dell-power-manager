"""Transactional battery charge control through Linux power-supply sysfs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from powerdeck_backends.battery.charge_types import (
    ParsedChargeTypes,
    mode_from_charge_type,
    normalize_charge_type,
    parse_charge_types,
)
from powerdeck_core.errors import (
    CommandExecutionError,
    MissingCapabilityError,
    PermissionDeniedError,
    PowerDeckError,
    RollbackError,
    StateVerificationError,
)
from powerdeck_core.models import ChargeInterval, ChargeMode, SerializableModel
from powerdeck_core.validation import (
    validate_charge_interval,
    validate_charge_mode,
)

_DEFAULT_ROOT = Path("/sys/class/power_supply")
_SOURCE = "linux-power-supply-sysfs"

type ReadText = Callable[[Path], str | None]
type WriteText = Callable[[Path, str], None]


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
    def legacy_mode_path(self) -> Path:
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

    @property
    def mode_write_path(self) -> Path | None:
        if self.legacy_mode_path.exists():
            return self.legacy_mode_path
        if self.modes_path.exists():
            return self.modes_path
        return None


@dataclass(frozen=True, slots=True)
class _ModeSnapshot:
    parsed: ParsedChargeTypes
    current_raw: str | None
    current_mode: ChargeMode | None
    write_path: Path | None


@dataclass(frozen=True, slots=True)
class _ChargeSnapshot:
    mode: _ModeSnapshot
    interval: ChargeInterval | None


def _read_text(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    return value or None


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


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
                (
                    path
                    for path in self.root.iterdir()
                    if path.is_dir()
                ),
                key=lambda path: path.name,
            )
        except OSError:
            return ()

        interfaces: list[_BatteryInterface] = []
        for directory in directories:
            interface = _BatteryInterface(directory)
            if self._read_text(interface.type_path) != "Battery":
                continue
            if (
                interface.modes_path.exists()
                or interface.legacy_mode_path.exists()
                or interface.start_path.exists()
                or interface.end_path.exists()
            ):
                interfaces.append(interface)
        return tuple(interfaces)

    def _require_interface(self) -> _BatteryInterface:
        interfaces = self._interfaces()
        if not interfaces:
            raise MissingCapabilityError(
                "No battery charge-control interface was found.",
                component="battery",
            )
        return interfaces[0]

    def _read_mode_snapshot(
        self,
        interface: _BatteryInterface,
    ) -> _ModeSnapshot:
        parsed = parse_charge_types(
            self._read_text(interface.modes_path)
        )
        legacy_raw = self._read_text(interface.legacy_mode_path)
        current_raw = legacy_raw or parsed.active_raw
        return _ModeSnapshot(
            parsed=parsed,
            current_raw=current_raw,
            current_mode=mode_from_charge_type(current_raw),
            write_path=interface.mode_write_path,
        )

    def _read_interval(
        self,
        interface: _BatteryInterface,
    ) -> ChargeInterval | None:
        start = _read_percent(self._read_text, interface.start_path)
        end = _read_percent(self._read_text, interface.end_path)
        if start is None or end is None:
            return None
        return ChargeInterval(start, end)

    def _snapshot(
        self,
        interface: _BatteryInterface,
    ) -> _ChargeSnapshot:
        return _ChargeSnapshot(
            mode=self._read_mode_snapshot(interface),
            interval=self._read_interval(interface),
        )

    def _read_status(
        self,
        interface: _BatteryInterface,
    ) -> ChargeControlStatus:
        snapshot = self._snapshot(interface)
        return ChargeControlStatus(
            battery_name=interface.directory.name,
            current_mode=snapshot.mode.current_mode,
            available_modes=snapshot.mode.parsed.available_modes,
            interval=snapshot.interval,
            source=_SOURCE,
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

    def _require_mode_write(
        self,
        snapshot: _ModeSnapshot,
    ) -> Path:
        if snapshot.write_path is None:
            raise MissingCapabilityError(
                "The battery exposes no writable charge-mode file.",
                component="battery",
            )
        if snapshot.current_raw is None:
            raise MissingCapabilityError(
                "The active charging mode cannot be snapshotted safely.",
                component="battery",
            )
        return snapshot.write_path

    def _write_mode_raw(
        self,
        snapshot: _ModeSnapshot,
        raw: str,
    ) -> None:
        self._write(
            self._require_mode_write(snapshot),
            raw,
        )

    def _mode_matches(
        self,
        interface: _BatteryInterface,
        raw: str,
    ) -> bool:
        current = self._read_mode_snapshot(interface).current_raw
        if current is None:
            return False
        return (
            normalize_charge_type(current)
            == normalize_charge_type(raw)
        )

    def _rollback_mode(
        self,
        interface: _BatteryInterface,
        before: _ModeSnapshot,
    ) -> None:
        if before.current_raw is None:
            raise RollbackError(
                "The previous charging mode was unavailable for rollback.",
                component="battery",
            )
        self._write_mode_raw(before, before.current_raw)
        if not self._mode_matches(interface, before.current_raw):
            raise RollbackError(
                "Battery mode rollback verification failed.",
                component="battery",
                details={"previous_raw": before.current_raw},
            )

    def apply_mode(
        self,
        value: str | ChargeMode,
    ) -> ChargeApplyResult:
        interface = self._require_interface()
        before = self._snapshot(interface)
        requested = validate_charge_mode(
            value,
            before.mode.parsed.available_modes,
        )
        target_raw = before.mode.parsed.raw_for_mode(requested)
        if target_raw is None:
            raise MissingCapabilityError(
                f"Charging mode is unavailable: {requested.value}",
                component="battery",
            )

        self._require_mode_write(before.mode)

        if before.mode.current_mode is requested:
            return ChargeApplyResult(
                battery_name=interface.directory.name,
                requested_mode=requested,
                previous_mode=before.mode.current_mode,
                current_mode=requested,
                previous_interval=before.interval,
                current_interval=before.interval,
                changed=False,
                verified=True,
                source=_SOURCE,
            )

        try:
            self._write_mode_raw(before.mode, target_raw)
        except PowerDeckError:
            if not self._mode_matches(
                interface,
                before.mode.current_raw or "",
            ):
                self._rollback_mode(interface, before.mode)
            raise

        after = self._snapshot(interface)
        if after.mode.current_mode is requested:
            return ChargeApplyResult(
                battery_name=interface.directory.name,
                requested_mode=requested,
                previous_mode=before.mode.current_mode,
                current_mode=requested,
                previous_interval=before.interval,
                current_interval=after.interval,
                changed=True,
                verified=True,
                source=_SOURCE,
            )

        self._rollback_mode(interface, before.mode)
        raise StateVerificationError(
            "Battery mode verification failed; the previous mode was restored.",
            component="battery",
            details={
                "requested": requested.value,
                "observed": (
                    None
                    if after.mode.current_mode is None
                    else after.mode.current_mode.value
                ),
            },
        )

    def _write_interval(
        self,
        interface: _BatteryInterface,
        interval: ChargeInterval,
        current: ChargeInterval,
    ) -> None:
        if interval.end_percent > current.end_percent:
            self._write(
                interface.end_path,
                str(interval.end_percent),
            )
            self._write(
                interface.start_path,
                str(interval.start_percent),
            )
        else:
            self._write(
                interface.start_path,
                str(interval.start_percent),
            )
            self._write(
                interface.end_path,
                str(interval.end_percent),
            )

    def _rollback_custom(
        self,
        interface: _BatteryInterface,
        before: _ChargeSnapshot,
    ) -> None:
        failures: list[str] = []

        if before.interval is not None:
            current_interval = (
                self._read_interval(interface)
                or before.interval
            )
            try:
                self._write_interval(
                    interface,
                    before.interval,
                    current_interval,
                )
            except PowerDeckError as error:
                failures.append(f"thresholds: {error.message}")

        try:
            self._rollback_mode(interface, before.mode)
        except PowerDeckError as error:
            failures.append(f"mode: {error.message}")

        restored = self._snapshot(interface)
        mode_ok = (
            before.mode.current_raw is not None
            and restored.mode.current_raw is not None
            and normalize_charge_type(restored.mode.current_raw)
            == normalize_charge_type(before.mode.current_raw)
        )
        interval_ok = restored.interval == before.interval

        if failures or not mode_ok or not interval_ok:
            raise RollbackError(
                "Custom charging rollback failed.",
                component="battery",
                details={
                    "failures": failures,
                    "mode_restored": mode_ok,
                    "interval_restored": interval_ok,
                },
            )

    def apply_custom(
        self,
        start_percent: object,
        end_percent: object,
    ) -> ChargeApplyResult:
        interface = self._require_interface()
        before = self._snapshot(interface)

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
            before.mode.parsed.available_modes,
        )
        target_raw = before.mode.parsed.raw_for_mode(
            ChargeMode.CUSTOM
        )
        if target_raw is None:
            raise MissingCapabilityError(
                "Custom charging mode is unavailable.",
                component="battery",
            )

        self._require_mode_write(before.mode)

        try:
            if before.mode.current_mode is not ChargeMode.CUSTOM:
                self._write_mode_raw(before.mode, target_raw)
                if not self._mode_matches(interface, target_raw):
                    raise StateVerificationError(
                        "Custom charging mode could not be activated.",
                        component="battery",
                    )

            current_interval = (
                self._read_interval(interface)
                or before.interval
            )
            self._write_interval(
                interface,
                requested_interval,
                current_interval,
            )
        except PowerDeckError:
            self._rollback_custom(interface, before)
            raise

        after = self._snapshot(interface)
        if (
            after.mode.current_mode is ChargeMode.CUSTOM
            and after.interval == requested_interval
        ):
            return ChargeApplyResult(
                battery_name=interface.directory.name,
                requested_mode=ChargeMode.CUSTOM,
                previous_mode=before.mode.current_mode,
                current_mode=ChargeMode.CUSTOM,
                previous_interval=before.interval,
                current_interval=requested_interval,
                changed=(
                    before.mode.current_mode is not ChargeMode.CUSTOM
                    or before.interval != requested_interval
                ),
                verified=True,
                source=_SOURCE,
            )

        self._rollback_custom(interface, before)
        raise StateVerificationError(
            "Custom charging verification failed; previous settings were restored.",
            component="battery",
        )


__all__ = [
    "ChargeApplyResult",
    "ChargeControlStatus",
    "SysfsChargeController",
]
