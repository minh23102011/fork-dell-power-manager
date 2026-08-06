"""Read-only system power-manager discovery."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from typing import Protocol

from powerdeck_core.models import PowerManagerState, ServiceActivity, ServiceState

_KNOWN_SERVICES: tuple[tuple[str, str], ...] = (
    ("power-profiles-daemon", "power-profiles-daemon.service"),
    ("tuned", "tuned.service"),
    ("tuned-ppd", "tuned-ppd.service"),
    ("tlp", "tlp.service"),
    ("auto-cpufreq", "auto-cpufreq.service"),
)
_PROFILE_PATTERN = re.compile(r"^\s*\*?\s*([a-z0-9][a-z0-9-]*):\s*$")


class CommandRunner(Protocol):
    def __call__(
        self,
        args: Sequence[str],
        *,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]: ...


def _run_command(
    args: Sequence[str],
    *,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _activity_from_systemd(value: str | None) -> ServiceActivity:
    mapping = {
        "active": ServiceActivity.ACTIVE,
        "inactive": ServiceActivity.INACTIVE,
        "failed": ServiceActivity.FAILED,
    }
    if value is None:
        return ServiceActivity.UNKNOWN
    return mapping.get(value, ServiceActivity.UNKNOWN)


def _parse_systemctl_show(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key.strip()] = value.strip()
    return values


def _parse_profiles(output: str) -> tuple[str, ...]:
    profiles: list[str] = []
    for line in output.splitlines():
        match = _PROFILE_PATTERN.match(line)
        if match is None:
            continue
        profile = match.group(1)
        if profile not in profiles:
            profiles.append(profile)
    return tuple(profiles)


class PowerManagerReader:
    """Inspect systemd power managers and power-profiles-daemon state."""

    def __init__(
        self,
        runner: CommandRunner | None = None,
        timeout: float = 2.0,
    ) -> None:
        self.runner: CommandRunner = runner or _run_command
        self.timeout = timeout

    def _run(self, args: Sequence[str]) -> subprocess.CompletedProcess[str] | None:
        try:
            return self.runner(args, timeout=self.timeout)
        except (OSError, subprocess.SubprocessError):
            return None

    def _read_service(self, name: str, unit: str) -> ServiceState:
        result = self._run(
            (
                "systemctl",
                "show",
                "--property=LoadState",
                "--property=ActiveState",
                unit,
            )
        )
        if result is None:
            return ServiceState(name=name, activity=ServiceActivity.UNKNOWN)

        values = _parse_systemctl_show(result.stdout)
        load_state = values.get("LoadState")
        active_state = values.get("ActiveState")
        installed = None if load_state is None else load_state != "not-found"
        activity = (
            ServiceActivity.NOT_INSTALLED
            if installed is False
            else _activity_from_systemd(active_state)
        )
        stderr = result.stderr.strip()
        details = stderr if result.returncode != 0 and stderr else None
        return ServiceState(
            name=name,
            activity=activity,
            installed=installed,
            details=details,
        )

    def _read_power_profiles(self) -> tuple[str | None, tuple[str, ...]]:
        current_result = self._run(("powerprofilesctl", "get"))
        list_result = self._run(("powerprofilesctl", "list"))

        current = None
        if current_result is not None and current_result.returncode == 0:
            current = current_result.stdout.strip() or None

        profiles: tuple[str, ...] = ()
        if list_result is not None and list_result.returncode == 0:
            profiles = _parse_profiles(list_result.stdout)
        return current, profiles

    def read(self) -> PowerManagerState:
        services = tuple(self._read_service(name, unit) for name, unit in _KNOWN_SERVICES)
        active_names = tuple(
            service.name
            for service in services
            if service.activity is ServiceActivity.ACTIVE
        )
        provider = active_names[0] if len(active_names) == 1 else None

        current_profile: str | None = None
        available_profiles: tuple[str, ...] = ()
        if "power-profiles-daemon" in active_names:
            current_profile, available_profiles = self._read_power_profiles()

        return PowerManagerState(
            services=services,
            provider=provider,
            current_profile=current_profile,
            available_profiles=available_profiles,
        )


__all__ = ["CommandRunner", "PowerManagerReader"]
