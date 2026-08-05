"""Typed, serializable domain models shared by every PowerDeck component."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime
from enum import Enum, StrEnum
from pathlib import Path

type JSONScalar = bool | int | float | str | None
type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]


def to_primitive(value: object) -> JSONValue:
    """Convert supported model values into deterministic JSON-compatible values."""

    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Enum):
        return to_primitive(value.value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: to_primitive(getattr(value, item.name))
            for item in fields(value)
            if not item.name.startswith("_")
        }
    if isinstance(value, Mapping):
        converted: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"JSON object key must be str, got {type(key).__name__}")
            converted[key] = to_primitive(item)
        return converted
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [to_primitive(item) for item in value]
    if isinstance(value, set | frozenset):
        return [to_primitive(item) for item in sorted(value, key=repr)]
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


class SerializableModel:
    """Mixin providing stable JSON serialization for dataclass models."""

    def to_dict(self) -> dict[str, JSONValue]:
        result = to_primitive(self)
        if not isinstance(result, dict):
            raise TypeError("SerializableModel must serialize to an object")
        return result

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=indent,
            sort_keys=True,
        )


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ServiceActivity(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    FAILED = "failed"
    UNKNOWN = "unknown"
    NOT_INSTALLED = "not-installed"


class ChargeMode(StrEnum):
    ADAPTIVE = "adaptive"
    STANDARD = "standard"
    EXPRESS = "express"
    PRIMARILY_AC = "primarily_ac"
    CUSTOM = "custom"


class ThermalProfile(StrEnum):
    QUIET = "quiet"
    COOL = "cool"
    BALANCED = "balanced"
    PERFORMANCE = "performance"


class RadioKind(StrEnum):
    BLUETOOTH = "bluetooth"
    WLAN = "wlan"
    WWAN = "wwan"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class MachineInfo(SerializableModel):
    vendor: str | None = None
    product_name: str | None = None
    product_family: str | None = None
    product_sku: str | None = None
    product_version: str | None = None
    board_name: str | None = None
    board_version: str | None = None
    bios_vendor: str | None = None
    bios_version: str | None = None
    bios_date: str | None = None
    os_name: str | None = None
    os_id: str | None = None
    kernel_release: str | None = None
    architecture: str | None = None


@dataclass(frozen=True, slots=True)
class ChargeInterval(SerializableModel):
    start_percent: int
    end_percent: int


@dataclass(frozen=True, slots=True)
class BatteryInfo(SerializableModel):
    name: str
    path: str | None = None
    present: bool | None = None
    status: str | None = None
    capacity_percent: int | None = None
    capacity_level: str | None = None
    technology: str | None = None
    manufacturer: str | None = None
    model_name: str | None = None
    serial_number: str | None = None
    cycle_count: int | None = None
    energy_now_wh: float | None = None
    energy_full_wh: float | None = None
    energy_full_design_wh: float | None = None
    charge_now_ah: float | None = None
    charge_full_ah: float | None = None
    charge_full_design_ah: float | None = None
    power_now_w: float | None = None
    current_now_a: float | None = None
    voltage_now_v: float | None = None
    temperature_celsius: float | None = None
    charge_types: tuple[str, ...] = ()
    active_charge_type: str | None = None
    charge_control_start_percent: int | None = None
    charge_control_end_percent: int | None = None

    @property
    def health_percent(self) -> float | None:
        if self.energy_full_wh is not None and self.energy_full_design_wh:
            return round((self.energy_full_wh / self.energy_full_design_wh) * 100.0, 1)
        if self.charge_full_ah is not None and self.charge_full_design_ah:
            return round((self.charge_full_ah / self.charge_full_design_ah) * 100.0, 1)
        return None


@dataclass(frozen=True, slots=True)
class ChargeCapabilities(SerializableModel):
    available: bool = False
    provider: str | None = None
    supported_modes: tuple[ChargeMode, ...] = ()
    custom_thresholds: bool = False
    start_min_percent: int | None = None
    start_max_percent: int | None = None
    end_min_percent: int | None = None
    end_max_percent: int | None = None
    minimum_gap_percent: int | None = None
    writable: bool = False


@dataclass(frozen=True, slots=True)
class ChargeState(SerializableModel):
    battery_name: str | None = None
    mode: ChargeMode | None = None
    interval: ChargeInterval | None = None
    source: str | None = None


@dataclass(frozen=True, slots=True)
class ThermalCapabilities(SerializableModel):
    available: bool = False
    provider: str | None = None
    supported_profiles: tuple[ThermalProfile, ...] = ()
    writable: bool = False


@dataclass(frozen=True, slots=True)
class ThermalState(SerializableModel):
    current_profile: ThermalProfile | None = None
    temperatures_celsius: dict[str, float] | None = None
    source: str | None = None


@dataclass(frozen=True, slots=True)
class CpuCapabilities(SerializableModel):
    model_name: str | None = None
    scaling_driver: str | None = None
    available_governors: tuple[str, ...] = ()
    current_governor: str | None = None
    minimum_frequency_mhz: float | None = None
    maximum_frequency_mhz: float | None = None
    intel_pstate_status: str | None = None
    turbo_control: bool = False
    max_performance_control: bool = False
    min_performance_control: bool = False


@dataclass(frozen=True, slots=True)
class ServiceState(SerializableModel):
    name: str
    activity: ServiceActivity
    installed: bool | None = None
    details: str | None = None


@dataclass(frozen=True, slots=True)
class PowerManagerState(SerializableModel):
    services: tuple[ServiceState, ...] = ()
    provider: str | None = None
    current_profile: str | None = None
    available_profiles: tuple[str, ...] = ()

    @property
    def active_services(self) -> tuple[ServiceState, ...]:
        return tuple(service for service in self.services if service.activity is ServiceActivity.ACTIVE)

    @property
    def has_conflict(self) -> bool:
        known_managers = {
            "power-profiles-daemon",
            "tuned",
            "tuned-ppd",
            "tlp",
            "auto-cpufreq",
        }
        active = [service for service in self.active_services if service.name in known_managers]
        return len(active) > 1


@dataclass(frozen=True, slots=True)
class DisplayMode(SerializableModel):
    width: int
    height: int
    refresh_hz: float
    current: bool = False
    preferred: bool = False

    @property
    def label(self) -> str:
        return f"{self.width}x{self.height}@{self.refresh_hz:.3f}"


@dataclass(frozen=True, slots=True)
class DisplayOutput(SerializableModel):
    connector: str
    name: str | None = None
    internal: bool = False
    enabled: bool = True
    variable_refresh_rate_supported: bool | None = None
    variable_refresh_rate_enabled: bool | None = None
    modes: tuple[DisplayMode, ...] = ()

    @property
    def current_mode(self) -> DisplayMode | None:
        return next((mode for mode in self.modes if mode.current), None)


@dataclass(frozen=True, slots=True)
class BrightnessDevice(SerializableModel):
    name: str
    device_class: str
    current: int | None = None
    maximum: int | None = None
    current_percent: float | None = None


@dataclass(frozen=True, slots=True)
class KeyboardBacklightDevice(SerializableModel):
    name: str
    current_level: int | None = None
    maximum_level: int | None = None
    available_levels: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class AudioState(SerializableModel):
    available: bool = False
    sink_volume: float | None = None
    sink_muted: bool | None = None
    source_volume: float | None = None
    source_muted: bool | None = None
    backend: str | None = None


@dataclass(frozen=True, slots=True)
class RadioDevice(SerializableModel):
    index: int | None
    name: str
    kind: RadioKind = RadioKind.OTHER
    soft_blocked: bool | None = None
    hard_blocked: bool | None = None


@dataclass(frozen=True, slots=True)
class AcAdapterState(SerializableModel):
    name: str
    online: bool | None = None
    adapter_type: str | None = None
    manufacturer: str | None = None
    model_name: str | None = None


@dataclass(frozen=True, slots=True)
class DiagnosticIssue(SerializableModel):
    code: str
    severity: Severity
    message: str
    component: str | None = None
    hint: str | None = None
    details: dict[str, JSONValue] | None = None


@dataclass(frozen=True, slots=True)
class PowerDeckCapabilities(SerializableModel):
    schema_version: int = 1
    charge: ChargeCapabilities = field(default_factory=ChargeCapabilities)
    thermal: ThermalCapabilities = field(default_factory=ThermalCapabilities)
    cpu: CpuCapabilities = field(default_factory=CpuCapabilities)
    power_manager: PowerManagerState = field(default_factory=PowerManagerState)
    displays: tuple[DisplayOutput, ...] = ()
    brightness_devices: tuple[BrightnessDevice, ...] = ()
    keyboard_backlights: tuple[KeyboardBacklightDevice, ...] = ()
    audio_control: bool = False
    radio_control: bool = False
    ac_monitoring: bool = False


@dataclass(frozen=True, slots=True)
class PowerDeckStatus(SerializableModel):
    schema_version: int = 1
    machine: MachineInfo = field(default_factory=MachineInfo)
    batteries: tuple[BatteryInfo, ...] = ()
    charge: ChargeState = field(default_factory=ChargeState)
    thermal: ThermalState = field(default_factory=ThermalState)
    power_manager: PowerManagerState = field(default_factory=PowerManagerState)
    displays: tuple[DisplayOutput, ...] = ()
    brightness_devices: tuple[BrightnessDevice, ...] = ()
    keyboard_backlights: tuple[KeyboardBacklightDevice, ...] = ()
    audio: AudioState = field(default_factory=AudioState)
    radios: tuple[RadioDevice, ...] = ()
    ac_adapters: tuple[AcAdapterState, ...] = ()
    diagnostics: tuple[DiagnosticIssue, ...] = ()

    @property
    def on_ac_power(self) -> bool | None:
        known = [adapter.online for adapter in self.ac_adapters if adapter.online is not None]
        if not known:
            return None
        return any(known)


__all__ = [
    "AcAdapterState",
    "AudioState",
    "BatteryInfo",
    "BrightnessDevice",
    "ChargeCapabilities",
    "ChargeInterval",
    "ChargeMode",
    "ChargeState",
    "CpuCapabilities",
    "DiagnosticIssue",
    "DisplayMode",
    "DisplayOutput",
    "JSONScalar",
    "JSONValue",
    "KeyboardBacklightDevice",
    "MachineInfo",
    "PowerDeckCapabilities",
    "PowerDeckStatus",
    "PowerManagerState",
    "RadioDevice",
    "RadioKind",
    "SerializableModel",
    "ServiceActivity",
    "ServiceState",
    "Severity",
    "ThermalCapabilities",
    "ThermalProfile",
    "ThermalState",
    "to_primitive",
]
