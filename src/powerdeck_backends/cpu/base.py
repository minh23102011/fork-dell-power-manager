"""Interfaces for read-only CPU discovery backends."""

from __future__ import annotations

from typing import Protocol

from powerdeck_core.models import CpuCapabilities


class CpuReader(Protocol):
    """Read CPU performance capabilities without mutating hardware."""

    def read_capabilities(self) -> CpuCapabilities: ...


__all__ = ["CpuReader"]
