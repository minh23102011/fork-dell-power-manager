"""Read-only desktop-session discovery backends."""

from powerdeck_backends.desktop.audio import WpctlAudioReader
from powerdeck_backends.desktop.backlight import SysfsBacklightReader
from powerdeck_backends.desktop.base import (
    AudioReader,
    BrightnessReader,
    DisplayReader,
    KeyboardBacklightReader,
)
from powerdeck_backends.desktop.niri import NiriOutputReader

__all__ = [
    "AudioReader",
    "BrightnessReader",
    "DisplayReader",
    "KeyboardBacklightReader",
    "NiriOutputReader",
    "SysfsBacklightReader",
    "WpctlAudioReader",
]
