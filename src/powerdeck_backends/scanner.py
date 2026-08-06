"""Aggregate read-only backends into one stable PowerDeck snapshot."""

from __future__ import annotations

from dataclasses import dataclass, replace

from powerdeck_backends.battery.base import BatteryReader
from powerdeck_backends.battery.sysfs_reader import SysfsBatteryReader
from powerdeck_backends.cpu.base import CpuReader
from powerdeck_backends.cpu.intel_pstate import IntelPstateReader
from powerdeck_backends.system.base import (
    AcAdapterReader,
    MachineReader,
    PowerManagerStateReader,
)
from powerdeck_backends.system.machine import MachineInfoReader
from powerdeck_backends.system.power_manager import PowerManagerReader
from powerdeck_backends.system.power_supply import SysfsAcAdapterReader
from powerdeck_backends.thermal.base import ThermalReader
from powerdeck_backends.thermal.platform_profile import PlatformProfileReader
from powerdeck_core.capabilities import build_diagnostics
from powerdeck_core.models import (
    PowerDeckCapabilities,
    PowerDeckStatus,
    SerializableModel,
)


@dataclass(frozen=True, slots=True)
class DiscoverySnapshot(SerializableModel):
    """Capabilities and current read-only state captured in one scan."""

    schema_version: int
    capabilities: PowerDeckCapabilities
    status: PowerDeckStatus


class PowerDeckScanner:
    """Coordinate all currently implemented read-only discovery backends."""

    def __init__(
        self,
        battery: BatteryReader | None = None,
        thermal: ThermalReader | None = None,
        cpu: CpuReader | None = None,
        machine: MachineReader | None = None,
        ac_adapters: AcAdapterReader | None = None,
        power_manager: PowerManagerStateReader | None = None,
    ) -> None:
        self.battery: BatteryReader = (
            battery if battery is not None else SysfsBatteryReader()
        )
        self.thermal: ThermalReader = (
            thermal if thermal is not None else PlatformProfileReader()
        )
        self.cpu: CpuReader = cpu if cpu is not None else IntelPstateReader()
        self.machine: MachineReader = (
            machine if machine is not None else MachineInfoReader()
        )
        self.ac_adapters: AcAdapterReader = (
            ac_adapters if ac_adapters is not None else SysfsAcAdapterReader()
        )
        self.power_manager: PowerManagerStateReader = (
            power_manager if power_manager is not None else PowerManagerReader()
        )

    def scan(self) -> DiscoverySnapshot:
        batteries = self.battery.read_batteries()
        charge_capabilities = self.battery.read_charge_capabilities()
        charge_state = self.battery.read_charge_state()
        thermal_capabilities = self.thermal.read_capabilities()
        thermal_state = self.thermal.read_state()
        cpu_capabilities = self.cpu.read_capabilities()
        machine = self.machine.read()
        ac_adapters = self.ac_adapters.read()
        power_manager = self.power_manager.read()

        capabilities = PowerDeckCapabilities(
            charge=charge_capabilities,
            thermal=thermal_capabilities,
            cpu=cpu_capabilities,
            power_manager=power_manager,
            ac_monitoring=any(adapter.online is not None for adapter in ac_adapters),
        )
        status = PowerDeckStatus(
            machine=machine,
            batteries=batteries,
            charge=charge_state,
            thermal=thermal_state,
            power_manager=power_manager,
            ac_adapters=ac_adapters,
        )
        status = replace(
            status,
            diagnostics=build_diagnostics(capabilities, status),
        )
        return DiscoverySnapshot(
            schema_version=1,
            capabilities=capabilities,
            status=status,
        )


__all__ = ["DiscoverySnapshot", "PowerDeckScanner"]
