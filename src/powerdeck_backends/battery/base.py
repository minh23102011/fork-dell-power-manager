"""Interfaces for read-only battery discovery backends."""

from __future__ import annotations

from typing import Protocol

from powerdeck_core.models import BatteryInfo, ChargeCapabilities, ChargeState


class BatteryReader(Protocol):
    """Read battery and charging state without mutating hardware."""

    def read_batteries(self) -> tuple[BatteryInfo, ...]: ...

    def read_charge_capabilities(self) -> ChargeCapabilities: ...

    def read_charge_state(self) -> ChargeState: ...


__all__ = ["BatteryReader"]
