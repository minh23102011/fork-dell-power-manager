"""Read Linux display and keyboard backlights from sysfs."""

from __future__ import annotations

from pathlib import Path

from powerdeck_core.models import BrightnessDevice, KeyboardBacklightDevice

_DEFAULT_BACKLIGHT_ROOT = Path("/sys/class/backlight")
_DEFAULT_LEDS_ROOT = Path("/sys/class/leds")
_MAX_ENUMERATED_KEYBOARD_LEVEL = 32


def _read_text(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    return value or None


def _read_int(path: Path) -> int | None:
    value = _read_text(path)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _device_paths(root: Path) -> tuple[Path, ...]:
    try:
        return tuple(
            sorted(
                (path for path in root.iterdir() if path.is_dir()),
                key=lambda path: path.name,
            )
        )
    except OSError:
        return ()


def _current_brightness(path: Path) -> int | None:
    actual = _read_int(path / "actual_brightness")
    if actual is not None:
        return actual
    return _read_int(path / "brightness")


def _brightness_percent(
    current: int | None,
    maximum: int | None,
) -> float | None:
    if current is None or maximum is None or maximum <= 0:
        return None
    if current < 0:
        return None
    return round((current / maximum) * 100.0, 1)


def _is_keyboard_backlight(name: str) -> bool:
    normalized = name.lower().replace("-", "_")
    return "kbd_backlight" in normalized or "keyboard_backlight" in normalized


class SysfsBacklightReader:
    """Read backlight classes without performing hardware writes."""

    def __init__(
        self,
        backlight_root: Path = _DEFAULT_BACKLIGHT_ROOT,
        leds_root: Path = _DEFAULT_LEDS_ROOT,
    ) -> None:
        self.backlight_root = backlight_root
        self.leds_root = leds_root

    def read_brightness_devices(self) -> tuple[BrightnessDevice, ...]:
        devices: list[BrightnessDevice] = []
        for path in _device_paths(self.backlight_root):
            current = _current_brightness(path)
            maximum = _read_int(path / "max_brightness")
            devices.append(
                BrightnessDevice(
                    name=path.name,
                    device_class=_read_text(path / "type") or "backlight",
                    current=current,
                    maximum=maximum,
                    current_percent=_brightness_percent(current, maximum),
                )
            )
        return tuple(devices)

    def read_keyboard_backlights(
        self,
    ) -> tuple[KeyboardBacklightDevice, ...]:
        devices: list[KeyboardBacklightDevice] = []
        for path in _device_paths(self.leds_root):
            if not _is_keyboard_backlight(path.name):
                continue

            current = _read_int(path / "brightness")
            maximum = _read_int(path / "max_brightness")
            levels: tuple[int, ...] = ()
            if (
                maximum is not None
                and 0 <= maximum <= _MAX_ENUMERATED_KEYBOARD_LEVEL
            ):
                levels = tuple(range(maximum + 1))

            devices.append(
                KeyboardBacklightDevice(
                    name=path.name,
                    current_level=current,
                    maximum_level=maximum,
                    available_levels=levels,
                )
            )
        return tuple(devices)


__all__ = ["SysfsBacklightReader"]
