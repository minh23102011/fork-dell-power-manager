"""Interfaces for read-only thermal discovery backends."""

from __future__ import annotations

from typing import Protocol

from powerdeck_core.models import ThermalCapabilities, ThermalState


class ThermalReader(Protocol):
    """Read thermal profile capabilities and state without mutating hardware."""

    def read_capabilities(self) -> ThermalCapabilities: ...

    def read_state(self) -> ThermalState: ...


__all__ = ["ThermalReader"]
