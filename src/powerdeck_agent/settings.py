"""Persistent Battery Saver settings for the user-session agent."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_SETTINGS_PATH = Path(
    "~/.config/powerdeck/saver.json"
).expanduser()


@dataclass(frozen=True, slots=True)
class SaverSettings:
    enabled: bool = True
    auto_enable_on_battery: bool = True
    restore_on_ac: bool = True
    brightness_cap_percent: int = 40
    only_lower_brightness: bool = True
    target_refresh_rate_hz: float = 60.0
    power_profile: str = "power-saver"
    thermal_profile: str = "quiet"
    disable_turbo: bool = True
    max_performance_percent: int = 60
    keyboard_backlight_level: int = 0
    mute_audio: bool = False


def _boolean(raw: dict[str, Any], key: str, default: bool) -> bool:
    value = raw.get(key, default)
    return value if isinstance(value, bool) else default


def _integer(
    raw: dict[str, Any],
    key: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    value = raw.get(key, default)
    if isinstance(value, int) and not isinstance(value, bool):
        return min(max(value, minimum), maximum)
    return default


def _number(
    raw: dict[str, Any],
    key: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    value = raw.get(key, default)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return min(max(float(value), minimum), maximum)
    return default


def _string(raw: dict[str, Any], key: str, default: str) -> str:
    value = raw.get(key, default)
    return value if isinstance(value, str) and value else default


def settings_from_mapping(raw: dict[str, Any]) -> SaverSettings:
    defaults = SaverSettings()
    return SaverSettings(
        enabled=_boolean(raw, "enabled", defaults.enabled),
        auto_enable_on_battery=_boolean(
            raw,
            "auto_enable_on_battery",
            defaults.auto_enable_on_battery,
        ),
        restore_on_ac=_boolean(
            raw,
            "restore_on_ac",
            defaults.restore_on_ac,
        ),
        brightness_cap_percent=_integer(
            raw,
            "brightness_cap_percent",
            defaults.brightness_cap_percent,
            1,
            100,
        ),
        only_lower_brightness=_boolean(
            raw,
            "only_lower_brightness",
            defaults.only_lower_brightness,
        ),
        target_refresh_rate_hz=_number(
            raw,
            "target_refresh_rate_hz",
            defaults.target_refresh_rate_hz,
            1.0,
            1000.0,
        ),
        power_profile=_string(
            raw,
            "power_profile",
            defaults.power_profile,
        ),
        thermal_profile=_string(
            raw,
            "thermal_profile",
            defaults.thermal_profile,
        ),
        disable_turbo=_boolean(
            raw,
            "disable_turbo",
            defaults.disable_turbo,
        ),
        max_performance_percent=_integer(
            raw,
            "max_performance_percent",
            defaults.max_performance_percent,
            1,
            100,
        ),
        keyboard_backlight_level=_integer(
            raw,
            "keyboard_backlight_level",
            defaults.keyboard_backlight_level,
            0,
            100,
        ),
        mute_audio=_boolean(
            raw,
            "mute_audio",
            defaults.mute_audio,
        ),
    )


def load_settings(
    path: Path = DEFAULT_SETTINGS_PATH,
) -> SaverSettings:
    expanded = path.expanduser()
    try:
        raw = json.loads(expanded.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return SaverSettings()
    return (
        settings_from_mapping(raw)
        if isinstance(raw, dict)
        else SaverSettings()
    )


def save_settings(
    settings: SaverSettings,
    path: Path = DEFAULT_SETTINGS_PATH,
) -> None:
    expanded = path.expanduser()
    expanded.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{expanded.name}.",
        dir=expanded.parent,
        text=True,
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                asdict(settings),
                stream,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(expanded)
    finally:
        temporary_path.unlink(missing_ok=True)


__all__ = [
    "DEFAULT_SETTINGS_PATH",
    "SaverSettings",
    "load_settings",
    "save_settings",
    "settings_from_mapping",
]
