"""Thermal profile discovery backends."""

from powerdeck_backends.thermal.base import ThermalReader
from powerdeck_backends.thermal.platform_profile import PlatformProfileReader

__all__ = ["PlatformProfileReader", "ThermalReader"]
