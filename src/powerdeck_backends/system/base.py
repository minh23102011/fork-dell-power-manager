"""Interfaces for read-only system discovery backends."""

from __future__ import annotations

from typing import Protocol

from powerdeck_core.models import AcAdapterState, MachineInfo, PowerManagerState


class MachineReader(Protocol):
    def read(self) -> MachineInfo: ...


class AcAdapterReader(Protocol):
    def read(self) -> tuple[AcAdapterState, ...]: ...


class PowerManagerStateReader(Protocol):
    def read(self) -> PowerManagerState: ...


__all__ = ["AcAdapterReader", "MachineReader", "PowerManagerStateReader"]
