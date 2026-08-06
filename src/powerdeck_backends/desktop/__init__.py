"""Read-only desktop-session discovery backends."""

from powerdeck_backends.desktop.backlight import SysfsBacklightReader
from powerdeck_backends.desktop.base import (
    BrightnessReader,
    DisplayReader,
    KeyboardBacklightReader,
)
from powerdeck_backends.desktop.niri import NiriOutputReader

__all__ = [
    "BrightnessReader",
    "DisplayReader",
    "KeyboardBacklightReader",
    "NiriOutputReader",
    "SysfsBacklightReader",
]
