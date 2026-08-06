"""Read-only system power-manager discovery."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from dataclasses import replace
from typing import Protocol

from powerdeck_core.models import PowerManagerState, ServiceActivity, ServiceState

_KNOWN_SERVICES: tuple[tuple[str, str], ...] = (
    ("power-profiles-daemon", "power-profiles-daemon.service"),
    ("tuned", "tuned.service"),
    ("tuned-ppd", "tuned-ppd.service"),
    ("tlp", "tlp.service"),
    ("auto-cpufreq", "auto-cpufreq.service"),
)
_KNOWN_PROFILES = ("power-saver", "balanced", "performance")
_PROFILE_TOKEN_PATTERN = re.compile(
    r"(?<![a-z0-9-])(power-saver|balanced|performance)(?![a-z0-9-])",
    re.IGNORECASE,
)
_BUS_NAME = "org.freedesktop.UPower.PowerProfiles"
_BUS_PATH = "/org/freedesktop/UPower/PowerProfiles"
_BUS_INTERFACE = "org.freedesktop.UPower.PowerProfiles"


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
    for match in _PROFILE_TOKEN_PATTERN.finditer(output):
        profile = match.group(1).lower()
        if profile not in profiles:
            profiles.append(profile)
    return tuple(profiles)


def _parse_busctl_string(output: str) -> str | None:
    match = re.fullmatch(r'\s*s\s+"([^"]+)"\s*', output)
    if match is None:
        return None
    value = match.group(1).strip()
    return value or None


def _command_failure(
    label: str,
    result: subprocess.CompletedProcess[str] | None,
) -> str:
    if result is None:
        return f"{label} could not be executed"

    detail = result.stderr.strip() or result.stdout.strip()
    if detail:
        return f"{label} exited with status {result.returncode}: {detail}"
    return f"{label} exited with status {result.returncode}"


class PowerManagerReader:
    """Inspect systemd power managers and power-profiles-daemon state."""

    def __init__(
        self,
        runner: CommandRunner | None = None,
        timeout: float = 2.0,
    ) -> None:
        self.runner: CommandRunner = runner or _run_command
        self.timeout = timeout

    def _run(
        self,
        args: Sequence[str],
    ) -> subprocess.CompletedProcess[str] | None:
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
            return ServiceState(
                name=name,
                activity=ServiceActivity.UNKNOWN,
            )

        values = _parse_systemctl_show(result.stdout)
        load_state = values.get("LoadState")
        active_state = values.get("ActiveState")
        installed = (
            None
            if load_state is None
            else load_state != "not-found"
        )
        activity = (
            ServiceActivity.NOT_INSTALLED
            if installed is False
            else _activity_from_systemd(active_state)
        )
        stderr = result.stderr.strip()
        details = (
            stderr
            if result.returncode != 0 and stderr
            else None
        )
        return ServiceState(
            name=name,
            activity=activity,
            installed=installed,
            details=details,
        )

    def _read_powerprofilesctl(
        self,
    ) -> tuple[
        str | None,
        tuple[str, ...],
        subprocess.CompletedProcess[str] | None,
        subprocess.CompletedProcess[str] | None,
    ]:
        current_result = self._run(("powerprofilesctl", "get"))
        list_result = self._run(("powerprofilesctl", "list"))

        current: str | None = None
        if (
            current_result is not None
            and current_result.returncode == 0
        ):
            candidate = current_result.stdout.strip().lower()
            if candidate in _KNOWN_PROFILES:
                current = candidate

        profiles: tuple[str, ...] = ()
        if list_result is not None and list_result.returncode == 0:
            profiles = _parse_profiles(list_result.stdout)

        return current, profiles, current_result, list_result

    def _read_bus_properties(
        self,
        *,
        need_current: bool,
        need_profiles: bool,
    ) -> tuple[
        str | None,
        tuple[str, ...],
        subprocess.CompletedProcess[str] | None,
        subprocess.CompletedProcess[str] | None,
    ]:
        current_result: subprocess.CompletedProcess[str] | None = None
        profiles_result: subprocess.CompletedProcess[str] | None = None
        current: str | None = None
        profiles: tuple[str, ...] = ()

        if need_current:
            current_result = self._run(
                (
                    "busctl",
                    "--system",
                    "get-property",
                    _BUS_NAME,
                    _BUS_PATH,
                    _BUS_INTERFACE,
                    "ActiveProfile",
                )
            )
            if (
                current_result is not None
                and current_result.returncode == 0
            ):
                candidate = _parse_busctl_string(
                    current_result.stdout
                )
                if candidate in _KNOWN_PROFILES:
                    current = candidate

        if need_profiles:
            profiles_result = self._run(
                (
                    "busctl",
                    "--system",
                    "get-property",
                    _BUS_NAME,
                    _BUS_PATH,
                    _BUS_INTERFACE,
                    "Profiles",
                )
            )
            if (
                profiles_result is not None
                and profiles_result.returncode == 0
            ):
                profiles = _parse_profiles(
                    profiles_result.stdout
                )

        return (
            current,
            profiles,
            current_result,
            profiles_result,
        )

    def _read_power_profiles(
        self,
    ) -> tuple[str | None, tuple[str, ...], tuple[str, ...]]:
        (
            current,
            profiles,
            current_result,
            list_result,
        ) = self._read_powerprofilesctl()

        (
            fallback_current,
            fallback_profiles,
            bus_current_result,
            bus_profiles_result,
        ) = self._read_bus_properties(
            need_current=current is None,
            need_profiles=not profiles,
        )

        if current is None:
            current = fallback_current
        if not profiles:
            profiles = fallback_profiles

        if current is not None and current not in profiles:
            profiles = (*profiles, current)

        problems: list[str] = []
        if current is None:
            problems.append(
                _command_failure(
                    "powerprofilesctl get",
                    current_result,
                )
            )
            problems.append(
                _command_failure(
                    "busctl ActiveProfile",
                    bus_current_result,
                )
            )

        if not profiles:
            problems.append(
                _command_failure(
                    "powerprofilesctl list",
                    list_result,
                )
            )
            problems.append(
                _command_failure(
                    "busctl Profiles",
                    bus_profiles_result,
                )
            )

        return current, profiles, tuple(problems)

    @staticmethod
    def _attach_profile_details(
        services: tuple[ServiceState, ...],
        problems: tuple[str, ...],
    ) -> tuple[ServiceState, ...]:
        if not problems:
            return services

        detail = "; ".join(problems)
        updated: list[ServiceState] = []
        for service in services:
            if service.name != "power-profiles-daemon":
                updated.append(service)
                continue

            combined = "; ".join(
                item
                for item in (service.details, detail)
                if item
            )
            updated.append(
                replace(
                    service,
                    details=combined or None,
                )
            )
        return tuple(updated)

    def read(self) -> PowerManagerState:
        services = tuple(
            self._read_service(name, unit)
            for name, unit in _KNOWN_SERVICES
        )
        active_names = tuple(
            service.name
            for service in services
            if service.activity is ServiceActivity.ACTIVE
        )
        provider = (
            active_names[0]
            if len(active_names) == 1
            else None
        )

        current_profile: str | None = None
        available_profiles: tuple[str, ...] = ()
        if "power-profiles-daemon" in active_names:
            (
                current_profile,
                available_profiles,
                problems,
            ) = self._read_power_profiles()
            services = self._attach_profile_details(
                services,
                problems,
            )

        return PowerManagerState(
            services=services,
            provider=provider,
            current_profile=current_profile,
            available_profiles=available_profiles,
        )


__all__ = ["CommandRunner", "PowerManagerReader"]
