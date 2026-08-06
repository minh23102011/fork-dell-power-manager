"""Read-only machine, AC adapter, and power-manager discovery."""

from powerdeck_backends.system.base import (
    AcAdapterReader,
    MachineReader,
    PowerManagerStateReader,
)
from powerdeck_backends.system.machine import MachineInfoReader
from powerdeck_backends.system.power_manager import PowerManagerReader
from powerdeck_backends.system.power_supply import SysfsAcAdapterReader

__all__ = [
    "AcAdapterReader",
    "MachineInfoReader",
    "MachineReader",
    "PowerManagerReader",
    "PowerManagerStateReader",
    "SysfsAcAdapterReader",
]
