"""Thermal profile discovery and control backends."""

from powerdeck_backends.thermal.base import ThermalReader
from powerdeck_backends.thermal.controller import (
    PlatformProfileController,
    ThermalControlStatus,
    ThermalProfileApplyResult,
)
from powerdeck_backends.thermal.platform_profile import PlatformProfileReader

__all__ = [
    "PlatformProfileController",
    "PlatformProfileReader",
    "ThermalControlStatus",
    "ThermalProfileApplyResult",
    "ThermalReader",
]
