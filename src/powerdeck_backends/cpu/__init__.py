"""CPU discovery backends."""

from powerdeck_backends.cpu.base import CpuReader
from powerdeck_backends.cpu.intel_pstate import IntelPstateReader

__all__ = ["CpuReader", "IntelPstateReader"]
