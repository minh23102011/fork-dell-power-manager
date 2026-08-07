from pathlib import Path

from powerdeck_backends.telemetry.power import (
    PowerTelemetrySampler,
    _parse_perf_event,
)


class Clock:
    def __init__(self) -> None:
        self.value = 10.0

    def __call__(self) -> float:
        return self.value


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def test_cpu_package_power_uses_rapl_delta(tmp_path: Path) -> None:
    powercap = tmp_path / "powercap"
    domain = powercap / "intel-rapl:0"
    _write(domain / "name", "package-0")
    _write(domain / "energy_uj", "1000000")
    _write(domain / "max_energy_range_uj", "100000000")

    clock = Clock()
    sampler = PowerTelemetrySampler(
        powercap_root=powercap,
        event_source_root=tmp_path / "events",
        drm_root=tmp_path / "drm",
        hwmon_root=tmp_path / "hwmon",
        monotonic=clock,
    )
    assert sampler.sample().cpu_watts is None

    clock.value = 11.0
    _write(domain / "energy_uj", "3500000")
    assert sampler.sample().cpu_watts == 2.5


def test_perf_event_is_derived_from_kernel_sysfs_abi(tmp_path: Path) -> None:
    pmu = tmp_path / "power"
    _write(pmu / "type", "9")
    _write(pmu / "cpumask", "2-5")
    _write(pmu / "events" / "energy-gpu", "event=0x3")
    _write(pmu / "events" / "energy-gpu.scale", "0.5")
    _write(pmu / "events" / "energy-gpu.unit", "Joules")
    _write(pmu / "format" / "event", "config:0-7")

    config = _parse_perf_event(pmu, "energy-gpu")

    assert config is not None
    assert config.event_type == 9
    assert config.config == 3
    assert config.cpu == 2
    assert config.scale == 0.5
    assert config.unit == "Joules"


def test_gpu_direct_hwmon_is_a_fallback(tmp_path: Path) -> None:
    drm = tmp_path / "drm"
    power = drm / "card0/device/hwmon/hwmon0/power1_average"
    _write(power, "2250000")

    sampler = PowerTelemetrySampler(
        powercap_root=tmp_path / "powercap",
        event_source_root=tmp_path / "events",
        drm_root=drm,
        hwmon_root=tmp_path / "hwmon",
    )
    assert sampler.sample().gpu_watts == 2.25
