"""Interfaces for read-only desktop-session discovery."""

from __future__ import annotations

from typing import Protocol

from powerdeck_core.models import (
    BrightnessDevice,
    DisplayOutput,
    KeyboardBacklightDevice,
)


class DisplayReader(Protocol):
    """Read compositor output state without changing it."""

    def read(self) -> tuple[DisplayOutput, ...]: ...


class BrightnessReader(Protocol):
    """Read display-backlight state without changing it."""

    def read_brightness_devices(self) -> tuple[BrightnessDevice, ...]: ...


class KeyboardBacklightReader(Protocol):
    """Read keyboard-backlight state without changing it."""

    def read_keyboard_backlights(
        self,
    ) -> tuple[KeyboardBacklightDevice, ...]: ...


__all__ = [
    "BrightnessReader",
    "DisplayReader",
    "KeyboardBacklightReader",
]
