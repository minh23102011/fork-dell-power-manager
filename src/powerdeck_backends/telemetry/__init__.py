"""Read-only privileged telemetry backends."""

from powerdeck_backends.telemetry.hwmon import FanReading, HwmonFanReader
from powerdeck_backends.telemetry.power import PowerTelemetrySample, PowerTelemetrySampler

__all__ = [
    "FanReading",
    "HwmonFanReader",
    "PowerTelemetrySample",
    "PowerTelemetrySampler",
]
