"""Read-only CPUFreq and Intel P-state discovery."""

from __future__ import annotations

import re
from pathlib import Path

from powerdeck_core.models import CpuCapabilities

_DEFAULT_CPUINFO_PATH = Path("/proc/cpuinfo")
_DEFAULT_CPUFREQ_ROOT = Path("/sys/devices/system/cpu/cpufreq")
_DEFAULT_INTEL_PSTATE_ROOT = Path("/sys/devices/system/cpu/intel_pstate")
_POLICY_SUFFIX_PATTERN = re.compile(r"(\d+)$")


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
        return int(value)
    except ValueError:
        return None


def _policy_sort_key(path: Path) -> tuple[int, str]:
    match = _POLICY_SUFFIX_PATTERN.search(path.name)
    if match is None:
        return (2**31 - 1, path.name)
    return (int(match.group(1)), path.name)


def _consensus(values: list[str]) -> str | None:
    unique = tuple(dict.fromkeys(values))
    if len(unique) == 1:
        return unique[0]
    return None


def _frequency_mhz(path: Path) -> float | None:
    value_khz = _read_int(path)
    if value_khz is None or value_khz <= 0:
        return None
    return round(value_khz / 1000.0, 3)


def _read_model_name(cpuinfo_path: Path) -> str | None:
    text = _read_text(cpuinfo_path)
    if text is None:
        return None

    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip().lower() in {"model name", "hardware"}:
            model_name = value.strip()
            if model_name:
                return model_name
    return None


class IntelPstateReader:
    """Read CPUFreq policies and Intel P-state controls without performing writes."""

    def __init__(
        self,
        cpuinfo_path: Path = _DEFAULT_CPUINFO_PATH,
        cpufreq_root: Path = _DEFAULT_CPUFREQ_ROOT,
        intel_pstate_root: Path = _DEFAULT_INTEL_PSTATE_ROOT,
    ) -> None:
        self.cpuinfo_path = cpuinfo_path
        self.cpufreq_root = cpufreq_root
        self.intel_pstate_root = intel_pstate_root

    def _policy_paths(self) -> tuple[Path, ...]:
        try:
            return tuple(
                sorted(
                    (
                        path
                        for path in self.cpufreq_root.iterdir()
                        if path.is_dir() and path.name.startswith("policy")
                    ),
                    key=_policy_sort_key,
                )
            )
        except OSError:
            return ()

    @staticmethod
    def _available_governors(
        policy_paths: tuple[Path, ...],
    ) -> tuple[str, ...]:
        governors: list[str] = []
        for policy in policy_paths:
            value = _read_text(policy / "scaling_available_governors")
            if value is None:
                continue
            for governor in value.split():
                if governor not in governors:
                    governors.append(governor)
        return tuple(governors)

    @staticmethod
    def _frequency_bounds(
        policy_paths: tuple[Path, ...],
    ) -> tuple[float | None, float | None]:
        minimums: list[float] = []
        maximums: list[float] = []

        for policy in policy_paths:
            minimum = _frequency_mhz(policy / "cpuinfo_min_freq")
            if minimum is None:
                minimum = _frequency_mhz(policy / "scaling_min_freq")
            if minimum is not None:
                minimums.append(minimum)

            maximum = _frequency_mhz(policy / "cpuinfo_max_freq")
            if maximum is None:
                maximum = _frequency_mhz(policy / "scaling_max_freq")
            if maximum is not None:
                maximums.append(maximum)

        return (
            min(minimums) if minimums else None,
            max(maximums) if maximums else None,
        )

    def read_capabilities(self) -> CpuCapabilities:
        policies = self._policy_paths()
        scaling_drivers = [
            value
            for policy in policies
            if (value := _read_text(policy / "scaling_driver")) is not None
        ]
        current_governors = [
            value
            for policy in policies
            if (value := _read_text(policy / "scaling_governor")) is not None
        ]
        minimum_frequency_mhz, maximum_frequency_mhz = self._frequency_bounds(
            policies
        )

        return CpuCapabilities(
            model_name=_read_model_name(self.cpuinfo_path),
            scaling_driver=_consensus(scaling_drivers),
            available_governors=self._available_governors(policies),
            current_governor=_consensus(current_governors),
            minimum_frequency_mhz=minimum_frequency_mhz,
            maximum_frequency_mhz=maximum_frequency_mhz,
            intel_pstate_status=_read_text(self.intel_pstate_root / "status"),
            turbo_control=(self.intel_pstate_root / "no_turbo").exists(),
            max_performance_control=(
                self.intel_pstate_root / "max_perf_pct"
            ).exists(),
            min_performance_control=(
                self.intel_pstate_root / "min_perf_pct"
            ).exists(),
        )


__all__ = ["IntelPstateReader"]
