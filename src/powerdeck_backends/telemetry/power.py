"""Privileged, low-overhead CPU/GPU/fan power telemetry.

CPU package power uses Intel RAPL ``energy_uj`` through the powercap class,
with the Linux ``power`` perf PMU ``energy-pkg`` event as a fallback.

Intel integrated GPU power uses the Linux ``power`` perf PMU ``energy-gpu``
event first, matching the mechanism used by modern resource monitors such as
btop. A direct DRM hwmon microwatt value is a compatibility fallback.

Fan RPM is read from Linux hwmon ``fan*_input`` tachometer files.
"""

from __future__ import annotations

import ctypes
import os
import platform
import struct
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from powerdeck_backends.telemetry.hwmon import HwmonFanReader
from powerdeck_core.models import SerializableModel

_PERF_FLAG_FD_CLOEXEC = 1 << 3


@dataclass(frozen=True, slots=True)
class PowerTelemetrySample(SerializableModel):
    cpu_watts: float | None = None
    gpu_watts: float | None = None
    fan_rpm: int | None = None
    cpu_source: str | None = None
    gpu_source: str | None = None
    fan_source: str | None = None


@dataclass(frozen=True, slots=True)
class _PerfConfig:
    event_type: int
    config: int
    config1: int
    config2: int
    cpu: int
    scale: float
    unit: str | None
    source: str


class _PerfEventAttr(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_uint32),
        ("size", ctypes.c_uint32),
        ("config", ctypes.c_uint64),
        ("sample_period", ctypes.c_uint64),
        ("sample_type", ctypes.c_uint64),
        ("read_format", ctypes.c_uint64),
        ("flags", ctypes.c_uint64),
        ("wakeup_events", ctypes.c_uint32),
        ("bp_type", ctypes.c_uint32),
        ("config1", ctypes.c_uint64),
        ("config2", ctypes.c_uint64),
    ]


def _read_text(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    return value or None


def _read_int(path: Path) -> int | None:
    value = _read_text(path)
    if value is None:
        return None
    try:
        return int(value, 0)
    except ValueError:
        return None


def _first_cpu(value: str | None) -> int:
    if not value:
        return 0
    token = value.split(",", maxsplit=1)[0].strip()
    token = token.split("-", maxsplit=1)[0].strip()
    try:
        return max(0, int(token))
    except ValueError:
        return 0


def _bit_positions(spec: str) -> tuple[int, ...]:
    positions: list[int] = []
    for part in spec.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            start_text, end_text = token.split("-", maxsplit=1)
            start = int(start_text)
            end = int(end_text)
            positions.extend(range(start, end + 1))
        else:
            positions.append(int(token))
    return tuple(positions)


def _pack_bits(current: int, value: int, positions: tuple[int, ...]) -> int:
    result = current
    for source_bit, target_bit in enumerate(positions):
        target_mask = 1 << target_bit
        result &= ~target_mask
        if value & (1 << source_bit):
            result |= target_mask
    return result


def _parse_perf_event(
    pmu_dir: Path,
    event_name: str,
) -> _PerfConfig | None:
    event_type = _read_int(pmu_dir / "type")
    event_spec = _read_text(pmu_dir / "events" / event_name)
    if event_type is None or event_spec is None:
        return None

    registers = {"config": 0, "config1": 0, "config2": 0}
    for assignment in event_spec.split(","):
        token = assignment.strip()
        if not token:
            continue
        if "=" in token:
            name, value_text = token.split("=", maxsplit=1)
            if value_text.strip() == "?":
                return None
            try:
                value = int(value_text, 0)
            except ValueError:
                return None
        else:
            name = token
            value = 1

        format_spec = _read_text(pmu_dir / "format" / name.strip())
        if format_spec is None or ":" not in format_spec:
            return None
        register, bits = format_spec.split(":", maxsplit=1)
        register = register.strip()
        if register not in registers:
            return None
        try:
            positions = _bit_positions(bits)
        except ValueError:
            return None
        registers[register] = _pack_bits(
            registers[register],
            value,
            positions,
        )

    scale_text = _read_text(pmu_dir / "events" / f"{event_name}.scale")
    try:
        scale = 1.0 if scale_text is None else float(scale_text)
    except ValueError:
        scale = 1.0

    return _PerfConfig(
        event_type=event_type,
        config=registers["config"],
        config1=registers["config1"],
        config2=registers["config2"],
        cpu=_first_cpu(_read_text(pmu_dir / "cpumask")),
        scale=scale,
        unit=_read_text(pmu_dir / "events" / f"{event_name}.unit"),
        source=str(pmu_dir / "events" / event_name),
    )


def _perf_event_open_number() -> int | None:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return 298
    if machine in {"aarch64", "arm64"}:
        return 241
    return None


class _PerfEnergyReader:
    def __init__(
        self,
        config: _PerfConfig | None,
    ) -> None:
        self.config = config
        self.fd: int | None = None
        self.previous: tuple[float, float] | None = None
        self.open_failed = False

    @property
    def source(self) -> str | None:
        return None if self.config is None else self.config.source

    def _open(self) -> bool:
        if self.fd is not None:
            return True
        if self.config is None or self.open_failed:
            return False

        syscall_number = _perf_event_open_number()
        if syscall_number is None:
            self.open_failed = True
            return False

        attr = _PerfEventAttr()
        attr.type = self.config.event_type
        attr.size = ctypes.sizeof(_PerfEventAttr)
        attr.config = self.config.config
        attr.config1 = self.config.config1
        attr.config2 = self.config.config2

        libc = ctypes.CDLL(None, use_errno=True)
        libc.syscall.restype = ctypes.c_long
        fd = libc.syscall(
            syscall_number,
            ctypes.byref(attr),
            -1,
            self.config.cpu,
            -1,
            _PERF_FLAG_FD_CLOEXEC,
        )
        if fd < 0:
            self.open_failed = True
            return False

        self.fd = int(fd)
        return True

    def _read_joules(self) -> float | None:
        if not self._open() or self.fd is None or self.config is None:
            return None
        try:
            payload = os.read(self.fd, 8)
        except OSError:
            return None
        if len(payload) != 8:
            return None
        count = struct.unpack("=Q", payload)[0]
        return float(count) * self.config.scale

    def watts(self, now: float) -> float | None:
        energy = self._read_joules()
        if energy is None:
            return None

        previous = self.previous
        self.previous = (energy, now)
        if previous is None:
            return None

        old_energy, old_time = previous
        elapsed = now - old_time
        delta = energy - old_energy
        if elapsed <= 0 or delta < 0:
            return None
        return round(delta / elapsed, 2)

    def close(self) -> None:
        if self.fd is None:
            return
        with suppress(OSError):
            os.close(self.fd)
        self.fd = None

    def __del__(self) -> None:
        self.close()


class _SysfsEnergyReader:
    def __init__(
        self,
        energy_path: Path | None,
        max_range_path: Path | None,
    ) -> None:
        self.energy_path = energy_path
        self.max_range_path = max_range_path
        self.previous: tuple[int, float] | None = None

    @property
    def source(self) -> str | None:
        return None if self.energy_path is None else str(self.energy_path)

    def watts(self, now: float) -> float | None:
        if self.energy_path is None:
            return None
        current = _read_int(self.energy_path)
        if current is None:
            return None

        previous = self.previous
        self.previous = (current, now)
        if previous is None:
            return None

        old_energy, old_time = previous
        elapsed = now - old_time
        if elapsed <= 0:
            return None

        delta = current - old_energy
        if delta < 0 and self.max_range_path is not None:
            maximum = _read_int(self.max_range_path)
            if maximum is not None and maximum > old_energy:
                delta = (maximum - old_energy) + current
        if delta < 0:
            return None
        return round((delta / 1_000_000.0) / elapsed, 2)


class _DirectMicrowattReader:
    def __init__(self, path: Path | None) -> None:
        self.path = path

    @property
    def source(self) -> str | None:
        return None if self.path is None else str(self.path)

    def watts(self) -> float | None:
        if self.path is None:
            return None
        value = _read_int(self.path)
        if value is None:
            return None
        return round(value / 1_000_000.0, 2)


def _discover_rapl_package(powercap_root: Path) -> _SysfsEnergyReader:
    if not powercap_root.is_dir():
        return _SysfsEnergyReader(None, None)

    fallback: Path | None = None
    for energy_path in sorted(powercap_root.glob("intel-rapl:*/energy_uj")):
        if fallback is None:
            fallback = energy_path
        name = (_read_text(energy_path.parent / "name") or "").lower()
        if name.startswith("package-"):
            maximum = energy_path.parent / "max_energy_range_uj"
            return _SysfsEnergyReader(
                energy_path,
                maximum if maximum.exists() else None,
            )

    if fallback is None:
        return _SysfsEnergyReader(None, None)
    maximum = fallback.parent / "max_energy_range_uj"
    return _SysfsEnergyReader(
        fallback,
        maximum if maximum.exists() else None,
    )


def _discover_direct_gpu_power(drm_root: Path) -> _DirectMicrowattReader:
    if not drm_root.is_dir():
        return _DirectMicrowattReader(None)

    for card in sorted(drm_root.glob("card[0-9]*")):
        hwmon_root = card / "device" / "hwmon"
        if not hwmon_root.is_dir():
            continue
        for hwmon in sorted(hwmon_root.glob("hwmon*")):
            for pattern in ("power*_average", "power*_input"):
                candidates = sorted(hwmon.glob(pattern))
                if candidates:
                    return _DirectMicrowattReader(candidates[0])
    return _DirectMicrowattReader(None)


class PowerTelemetrySampler:
    """Persistent sampler intended to live inside ``powerdeckd``."""

    def __init__(
        self,
        *,
        powercap_root: Path = Path("/sys/class/powercap"),
        event_source_root: Path = Path("/sys/bus/event_source/devices"),
        drm_root: Path = Path("/sys/class/drm"),
        hwmon_root: Path = Path("/sys/class/hwmon"),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.monotonic = monotonic
        self.lock = threading.Lock()
        self.fans = HwmonFanReader(hwmon_root)

        self.cpu_sysfs = _discover_rapl_package(powercap_root)
        power_pmu = event_source_root / "power"
        self.cpu_perf = _PerfEnergyReader(
            _parse_perf_event(power_pmu, "energy-pkg")
        )
        self.gpu_perf = _PerfEnergyReader(
            _parse_perf_event(power_pmu, "energy-gpu")
        )
        self.gpu_hwmon = _discover_direct_gpu_power(drm_root)

    def _cpu_watts(self, now: float) -> tuple[float | None, str | None]:
        value = self.cpu_sysfs.watts(now)
        if value is not None:
            return value, self.cpu_sysfs.source

        value = self.cpu_perf.watts(now)
        if value is not None:
            return value, self.cpu_perf.source

        return None, self.cpu_sysfs.source or self.cpu_perf.source

    def _gpu_watts(self, now: float) -> tuple[float | None, str | None]:
        value = self.gpu_perf.watts(now)
        if value is not None:
            return value, self.gpu_perf.source

        value = self.gpu_hwmon.watts()
        if value is not None:
            return value, self.gpu_hwmon.source

        return None, self.gpu_perf.source or self.gpu_hwmon.source

    def sample(self) -> PowerTelemetrySample:
        with self.lock:
            now = self.monotonic()
            cpu_watts, cpu_source = self._cpu_watts(now)
            gpu_watts, gpu_source = self._gpu_watts(now)

            fans = self.fans.read()
            first_fan = next((fan for fan in fans if fan.rpm is not None), None)

            return PowerTelemetrySample(
                cpu_watts=cpu_watts,
                gpu_watts=gpu_watts,
                fan_rpm=None if first_fan is None else first_fan.rpm,
                cpu_source=cpu_source,
                gpu_source=gpu_source,
                fan_source=None if first_fan is None else first_fan.source_path,
            )


__all__ = ["PowerTelemetrySample", "PowerTelemetrySampler"]
