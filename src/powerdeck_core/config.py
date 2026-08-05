"""Versioned, resilient TOML configuration with atomic writes."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from powerdeck_core.errors import InvalidConfigurationError, ValidationError
from powerdeck_core.models import (
    ChargeMode,
    DiagnosticIssue,
    JSONValue,
    SerializableModel,
    Severity,
    ThermalProfile,
)
from powerdeck_core.validation import (
    validate_brightness_cap,
    validate_charge_interval,
    validate_charge_mode,
    validate_cpu_performance_percent,
    validate_refresh_rate,
    validate_thermal_profile,
)

CONFIG_SCHEMA_VERSION = 1
DEFAULT_CONFIG_PATH = Path("~/.config/powerdeck/config.toml").expanduser()


@dataclass(frozen=True, slots=True)
class BatteryConfig(SerializableModel):
    preferred_mode: ChargeMode = ChargeMode.CUSTOM
    custom_start: int = 50
    custom_end: int = 80
    extra: dict[str, JSONValue] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class ThermalConfig(SerializableModel):
    preferred_mode: ThermalProfile = ThermalProfile.BALANCED
    extra: dict[str, JSONValue] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class DisplaySaverConfig(SerializableModel):
    brightness_cap_percent: int = 40
    only_lower_brightness: bool = True
    target_refresh_rate_hz: float = 60.0
    restore_refresh_rate: bool = True
    extra: dict[str, JSONValue] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class PerformanceSaverConfig(SerializableModel):
    power_profile: str = "power-saver"
    thermal_profile: ThermalProfile = ThermalProfile.QUIET
    disable_turbo: bool = True
    max_perf_percent: int = 60
    extra: dict[str, JSONValue] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class DeviceSaverConfig(SerializableModel):
    keyboard_backlight_level: int = 0
    mute_audio: bool = False
    disable_bluetooth: bool = False
    disable_wifi: bool = False
    extra: dict[str, JSONValue] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class BatterySaverConfig(SerializableModel):
    enabled: bool = True
    auto_enable_on_battery: bool = True
    restore_on_ac: bool = True
    rollback_on_failure: bool = True
    display: DisplaySaverConfig = field(default_factory=DisplaySaverConfig)
    performance: PerformanceSaverConfig = field(default_factory=PerformanceSaverConfig)
    devices: DeviceSaverConfig = field(default_factory=DeviceSaverConfig)
    extra: dict[str, JSONValue] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class PowerDeckConfig(SerializableModel):
    schema_version: int = CONFIG_SCHEMA_VERSION
    battery: BatteryConfig = field(default_factory=BatteryConfig)
    thermal: ThermalConfig = field(default_factory=ThermalConfig)
    battery_saver: BatterySaverConfig = field(default_factory=BatterySaverConfig)
    extra: dict[str, JSONValue] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class ConfigLoadResult(SerializableModel):
    config: PowerDeckConfig
    issues: tuple[DiagnosticIssue, ...] = ()
    source_exists: bool = False


class _Reader:
    def __init__(self) -> None:
        self.issues: list[DiagnosticIssue] = []

    def warn(self, code: str, message: str, *, field_name: str | None = None) -> None:
        self.issues.append(
            DiagnosticIssue(
                code=code,
                severity=Severity.WARNING,
                component="config",
                message=message,
                details={"field": field_name} if field_name else None,
            )
        )

    def table(self, source: dict[str, Any], key: str) -> dict[str, Any]:
        value = source.get(key, {})
        if isinstance(value, dict):
            return value
        self.warn("invalid-config-table", f"{key} must be a TOML table", field_name=key)
        return {}

    def boolean(self, source: dict[str, Any], key: str, default: bool) -> bool:
        value = source.get(key, default)
        if isinstance(value, bool):
            return value
        self.warn("invalid-config-value", f"{key} must be a boolean", field_name=key)
        return default

    def integer(self, source: dict[str, Any], key: str, default: int) -> int:
        value = source.get(key, default)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        self.warn("invalid-config-value", f"{key} must be an integer", field_name=key)
        return default

    def number(self, source: dict[str, Any], key: str, default: float) -> float:
        value = source.get(key, default)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
        self.warn("invalid-config-value", f"{key} must be numeric", field_name=key)
        return default

    def string(self, source: dict[str, Any], key: str, default: str) -> str:
        value = source.get(key, default)
        if isinstance(value, str):
            return value
        self.warn("invalid-config-value", f"{key} must be a string", field_name=key)
        return default


def _extra(source: dict[str, Any], known: set[str]) -> dict[str, JSONValue]:
    extras: dict[str, JSONValue] = {}
    for key, value in source.items():
        if key in known:
            continue
        try:
            extras[key] = _toml_value_to_json(value)
        except TypeError:
            continue
    return extras


def _toml_value_to_json(value: object) -> JSONValue:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list):
        return [_toml_value_to_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _toml_value_to_json(item) for key, item in value.items()}
    raise TypeError(f"unsupported TOML value: {type(value).__name__}")


def _parse_config(raw: dict[str, Any]) -> ConfigLoadResult:
    reader = _Reader()
    defaults = PowerDeckConfig()

    schema_version = reader.integer(raw, "schema_version", CONFIG_SCHEMA_VERSION)
    if schema_version != CONFIG_SCHEMA_VERSION:
        reader.warn(
            "unsupported-config-schema",
            f"Unsupported schema_version {schema_version}; using schema {CONFIG_SCHEMA_VERSION}",
            field_name="schema_version",
        )
        schema_version = CONFIG_SCHEMA_VERSION

    battery_raw = reader.table(raw, "battery")
    mode_text = reader.string(battery_raw, "preferred_mode", defaults.battery.preferred_mode.value)
    try:
        charge_mode = validate_charge_mode(mode_text)
    except ValidationError as error:
        reader.warn("invalid-config-value", error.message, field_name="battery.preferred_mode")
        charge_mode = defaults.battery.preferred_mode

    custom_start = reader.integer(battery_raw, "custom_start", defaults.battery.custom_start)
    custom_end = reader.integer(battery_raw, "custom_end", defaults.battery.custom_end)
    try:
        interval = validate_charge_interval(custom_start, custom_end)
        custom_start = interval.start_percent
        custom_end = interval.end_percent
    except ValidationError as error:
        reader.warn("invalid-config-value", error.message, field_name="battery.custom_start/custom_end")
        custom_start = defaults.battery.custom_start
        custom_end = defaults.battery.custom_end

    thermal_raw = reader.table(raw, "thermal")
    thermal_text = reader.string(
        thermal_raw,
        "preferred_mode",
        defaults.thermal.preferred_mode.value,
    )
    try:
        thermal_mode = validate_thermal_profile(thermal_text)
    except ValidationError as error:
        reader.warn("invalid-config-value", error.message, field_name="thermal.preferred_mode")
        thermal_mode = defaults.thermal.preferred_mode

    saver_raw = reader.table(raw, "battery_saver")
    display_raw = reader.table(saver_raw, "display")
    performance_raw = reader.table(saver_raw, "performance")
    devices_raw = reader.table(saver_raw, "devices")

    brightness_cap = reader.integer(
        display_raw,
        "brightness_cap_percent",
        defaults.battery_saver.display.brightness_cap_percent,
    )
    try:
        brightness_cap = validate_brightness_cap(brightness_cap)
    except ValidationError as error:
        reader.warn("invalid-config-value", error.message, field_name="battery_saver.display.brightness_cap_percent")
        brightness_cap = defaults.battery_saver.display.brightness_cap_percent

    refresh_rate = reader.number(
        display_raw,
        "target_refresh_rate_hz",
        defaults.battery_saver.display.target_refresh_rate_hz,
    )
    try:
        refresh_rate = validate_refresh_rate(refresh_rate)
    except ValidationError as error:
        reader.warn("invalid-config-value", error.message, field_name="battery_saver.display.target_refresh_rate_hz")
        refresh_rate = defaults.battery_saver.display.target_refresh_rate_hz

    saver_thermal_text = reader.string(
        performance_raw,
        "thermal_profile",
        defaults.battery_saver.performance.thermal_profile.value,
    )
    try:
        saver_thermal = validate_thermal_profile(saver_thermal_text)
    except ValidationError as error:
        reader.warn("invalid-config-value", error.message, field_name="battery_saver.performance.thermal_profile")
        saver_thermal = defaults.battery_saver.performance.thermal_profile

    max_perf = reader.integer(
        performance_raw,
        "max_perf_percent",
        defaults.battery_saver.performance.max_perf_percent,
    )
    try:
        max_perf = validate_cpu_performance_percent(max_perf)
    except ValidationError as error:
        reader.warn("invalid-config-value", error.message, field_name="battery_saver.performance.max_perf_percent")
        max_perf = defaults.battery_saver.performance.max_perf_percent

    keyboard_level = reader.integer(
        devices_raw,
        "keyboard_backlight_level",
        defaults.battery_saver.devices.keyboard_backlight_level,
    )
    if keyboard_level < 0:
        reader.warn(
            "invalid-config-value",
            "keyboard_backlight_level must be zero or greater",
            field_name="battery_saver.devices.keyboard_backlight_level",
        )
        keyboard_level = defaults.battery_saver.devices.keyboard_backlight_level

    config = PowerDeckConfig(
        schema_version=schema_version,
        battery=BatteryConfig(
            preferred_mode=charge_mode,
            custom_start=custom_start,
            custom_end=custom_end,
            extra=_extra(battery_raw, {"preferred_mode", "custom_start", "custom_end"}),
        ),
        thermal=ThermalConfig(
            preferred_mode=thermal_mode,
            extra=_extra(thermal_raw, {"preferred_mode"}),
        ),
        battery_saver=BatterySaverConfig(
            enabled=reader.boolean(saver_raw, "enabled", defaults.battery_saver.enabled),
            auto_enable_on_battery=reader.boolean(
                saver_raw,
                "auto_enable_on_battery",
                defaults.battery_saver.auto_enable_on_battery,
            ),
            restore_on_ac=reader.boolean(
                saver_raw,
                "restore_on_ac",
                defaults.battery_saver.restore_on_ac,
            ),
            rollback_on_failure=reader.boolean(
                saver_raw,
                "rollback_on_failure",
                defaults.battery_saver.rollback_on_failure,
            ),
            display=DisplaySaverConfig(
                brightness_cap_percent=brightness_cap,
                only_lower_brightness=reader.boolean(
                    display_raw,
                    "only_lower_brightness",
                    defaults.battery_saver.display.only_lower_brightness,
                ),
                target_refresh_rate_hz=refresh_rate,
                restore_refresh_rate=reader.boolean(
                    display_raw,
                    "restore_refresh_rate",
                    defaults.battery_saver.display.restore_refresh_rate,
                ),
                extra=_extra(
                    display_raw,
                    {
                        "brightness_cap_percent",
                        "only_lower_brightness",
                        "target_refresh_rate_hz",
                        "restore_refresh_rate",
                    },
                ),
            ),
            performance=PerformanceSaverConfig(
                power_profile=reader.string(
                    performance_raw,
                    "power_profile",
                    defaults.battery_saver.performance.power_profile,
                ),
                thermal_profile=saver_thermal,
                disable_turbo=reader.boolean(
                    performance_raw,
                    "disable_turbo",
                    defaults.battery_saver.performance.disable_turbo,
                ),
                max_perf_percent=max_perf,
                extra=_extra(
                    performance_raw,
                    {"power_profile", "thermal_profile", "disable_turbo", "max_perf_percent"},
                ),
            ),
            devices=DeviceSaverConfig(
                keyboard_backlight_level=keyboard_level,
                mute_audio=reader.boolean(
                    devices_raw,
                    "mute_audio",
                    defaults.battery_saver.devices.mute_audio,
                ),
                disable_bluetooth=reader.boolean(
                    devices_raw,
                    "disable_bluetooth",
                    defaults.battery_saver.devices.disable_bluetooth,
                ),
                disable_wifi=reader.boolean(
                    devices_raw,
                    "disable_wifi",
                    defaults.battery_saver.devices.disable_wifi,
                ),
                extra=_extra(
                    devices_raw,
                    {
                        "keyboard_backlight_level",
                        "mute_audio",
                        "disable_bluetooth",
                        "disable_wifi",
                    },
                ),
            ),
            extra=_extra(
                saver_raw,
                {
                    "enabled",
                    "auto_enable_on_battery",
                    "restore_on_ac",
                    "rollback_on_failure",
                    "display",
                    "performance",
                    "devices",
                },
            ),
        ),
        extra=_extra(raw, {"schema_version", "battery", "thermal", "battery_saver"}),
    )
    return ConfigLoadResult(config=config, issues=tuple(reader.issues), source_exists=True)


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> ConfigLoadResult:
    """Load a config resiliently; malformed input returns defaults plus diagnostics."""

    expanded = path.expanduser()
    if not expanded.exists():
        return ConfigLoadResult(config=PowerDeckConfig(), source_exists=False)
    try:
        with expanded.open("rb") as stream:
            raw = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        issue = DiagnosticIssue(
            code="config-load-failed",
            severity=Severity.ERROR,
            component="config",
            message="PowerDeck configuration could not be loaded; defaults are active.",
            hint=str(error),
        )
        return ConfigLoadResult(
            config=PowerDeckConfig(),
            issues=(issue,),
            source_exists=True,
        )
    return _parse_config(raw)


def validate_config(config: PowerDeckConfig) -> None:
    if config.schema_version != CONFIG_SCHEMA_VERSION:
        raise InvalidConfigurationError(
            f"unsupported configuration schema: {config.schema_version}",
            component="config",
        )
    validate_charge_mode(config.battery.preferred_mode)
    validate_charge_interval(config.battery.custom_start, config.battery.custom_end)
    validate_thermal_profile(config.thermal.preferred_mode)
    validate_brightness_cap(config.battery_saver.display.brightness_cap_percent)
    validate_refresh_rate(config.battery_saver.display.target_refresh_rate_hz)
    validate_thermal_profile(config.battery_saver.performance.thermal_profile)
    validate_cpu_performance_percent(config.battery_saver.performance.max_perf_percent)
    if config.battery_saver.devices.keyboard_backlight_level < 0:
        raise InvalidConfigurationError(
            "keyboard backlight level must be zero or greater",
            component="config",
        )


def _merge(extra: dict[str, JSONValue], known: dict[str, JSONValue]) -> dict[str, JSONValue]:
    result = dict(extra)
    result.update(known)
    return result


def config_to_mapping(config: PowerDeckConfig) -> dict[str, JSONValue]:
    validate_config(config)
    display = _merge(
        config.battery_saver.display.extra,
        {
            "brightness_cap_percent": config.battery_saver.display.brightness_cap_percent,
            "only_lower_brightness": config.battery_saver.display.only_lower_brightness,
            "target_refresh_rate_hz": config.battery_saver.display.target_refresh_rate_hz,
            "restore_refresh_rate": config.battery_saver.display.restore_refresh_rate,
        },
    )
    performance = _merge(
        config.battery_saver.performance.extra,
        {
            "power_profile": config.battery_saver.performance.power_profile,
            "thermal_profile": config.battery_saver.performance.thermal_profile.value,
            "disable_turbo": config.battery_saver.performance.disable_turbo,
            "max_perf_percent": config.battery_saver.performance.max_perf_percent,
        },
    )
    devices = _merge(
        config.battery_saver.devices.extra,
        {
            "keyboard_backlight_level": config.battery_saver.devices.keyboard_backlight_level,
            "mute_audio": config.battery_saver.devices.mute_audio,
            "disable_bluetooth": config.battery_saver.devices.disable_bluetooth,
            "disable_wifi": config.battery_saver.devices.disable_wifi,
        },
    )
    saver = _merge(
        config.battery_saver.extra,
        {
            "enabled": config.battery_saver.enabled,
            "auto_enable_on_battery": config.battery_saver.auto_enable_on_battery,
            "restore_on_ac": config.battery_saver.restore_on_ac,
            "rollback_on_failure": config.battery_saver.rollback_on_failure,
            "display": display,
            "performance": performance,
            "devices": devices,
        },
    )
    return _merge(
        config.extra,
        {
            "schema_version": config.schema_version,
            "battery": _merge(
                config.battery.extra,
                {
                    "preferred_mode": config.battery.preferred_mode.value,
                    "custom_start": config.battery.custom_start,
                    "custom_end": config.battery.custom_end,
                },
            ),
            "thermal": _merge(
                config.thermal.extra,
                {"preferred_mode": config.thermal.preferred_mode.value},
            ),
            "battery_saver": saver,
        },
    )


def _format_scalar(value: JSONValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_format_scalar(item) for item in value) + "]"
    if value is None:
        raise InvalidConfigurationError("TOML does not support null values", component="config")
    raise InvalidConfigurationError("nested tables must be emitted separately", component="config")


def _emit_table(data: dict[str, JSONValue], prefix: tuple[str, ...], lines: list[str]) -> None:
    scalars = {key: value for key, value in data.items() if not isinstance(value, dict)}
    tables = {key: value for key, value in data.items() if isinstance(value, dict)}

    if prefix:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append("[" + ".".join(prefix) + "]")
    for key in sorted(scalars):
        lines.append(f"{key} = {_format_scalar(scalars[key])}")
    for key in sorted(tables):
        table = tables[key]
        if isinstance(table, dict):
            _emit_table(table, (*prefix, key), lines)


def dumps_config(config: PowerDeckConfig) -> str:
    mapping = config_to_mapping(config)
    lines: list[str] = []
    _emit_table(mapping, (), lines)
    return "\n".join(lines).rstrip() + "\n"


def save_config_atomic(
    config: PowerDeckConfig,
    path: Path = DEFAULT_CONFIG_PATH,
    *,
    create_backup: bool = True,
) -> None:
    """Validate and atomically replace a config, preserving one backup."""

    expanded = path.expanduser()
    expanded.parent.mkdir(parents=True, exist_ok=True)
    payload = dumps_config(config)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=expanded.parent,
            prefix=f".{expanded.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

        if create_backup and expanded.exists():
            backup = expanded.with_suffix(expanded.suffix + ".bak")
            shutil.copy2(expanded, backup)
        os.replace(temporary_path, expanded)
        temporary_path = None
    except OSError as error:
        raise InvalidConfigurationError(
            f"failed to save configuration: {error}",
            component="config",
        ) from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


__all__ = [
    "BatteryConfig",
    "BatterySaverConfig",
    "CONFIG_SCHEMA_VERSION",
    "ConfigLoadResult",
    "DEFAULT_CONFIG_PATH",
    "DeviceSaverConfig",
    "DisplaySaverConfig",
    "PerformanceSaverConfig",
    "PowerDeckConfig",
    "ThermalConfig",
    "config_to_mapping",
    "dumps_config",
    "load_config",
    "save_config_atomic",
    "validate_config",
]
