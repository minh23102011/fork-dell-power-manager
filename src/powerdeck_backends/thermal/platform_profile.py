"""Read-only Linux platform-profile and thermal-zone discovery."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from powerdeck_core.models import ThermalCapabilities, ThermalProfile, ThermalState

_DEFAULT_PLATFORM_PROFILE_ROOT = Path("/sys/class/platform-profile")
_DEFAULT_ACPI_ROOT = Path("/sys/firmware/acpi")
_DEFAULT_THERMAL_ROOT = Path("/sys/class/thermal")


@dataclass(frozen=True, slots=True)
class _ProfileInterface:
    choices_path: Path
    profile_path: Path
    provider_path: Path | None
    source: str


def _read_text(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    return value or None


def _read_int(path: Path) -> int | None:
    text = _read_text(path)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _profile_from_token(value: str | None) -> ThermalProfile | None:
    if value is None:
        return None
    normalized = value.strip().lower().replace("-", "_")
    try:
        return ThermalProfile(normalized)
    except ValueError:
        return None


def _parse_profiles(value: str | None) -> tuple[ThermalProfile, ...]:
    if value is None:
        return ()

    profiles: list[ThermalProfile] = []
    for token in value.replace("[", " ").replace("]", " ").split():
        profile = _profile_from_token(token)
        if profile is not None and profile not in profiles:
            profiles.append(profile)
    return tuple(profiles)


def _temperature_celsius(path: Path) -> float | None:
    raw = _read_int(path)
    if raw is None:
        return None

    temperature = raw / 1000.0
    if temperature < -100.0 or temperature > 250.0:
        return None
    return round(temperature, 3)


class PlatformProfileReader:
    """Read kernel platform profiles and thermal zones without performing writes."""

    def __init__(
        self,
        platform_profile_root: Path = _DEFAULT_PLATFORM_PROFILE_ROOT,
        acpi_root: Path = _DEFAULT_ACPI_ROOT,
        thermal_root: Path = _DEFAULT_THERMAL_ROOT,
    ) -> None:
        self.platform_profile_root = platform_profile_root
        self.acpi_root = acpi_root
        self.thermal_root = thermal_root

    def _class_interfaces(self) -> tuple[_ProfileInterface, ...]:
        try:
            directories = sorted(
                (
                    path
                    for path in self.platform_profile_root.iterdir()
                    if path.is_dir()
                ),
                key=lambda path: path.name,
            )
        except OSError:
            return ()

        interfaces: list[_ProfileInterface] = []
        for directory in directories:
            choices_path = directory / "choices"
            profile_path = directory / "profile"
            if not choices_path.exists() and not profile_path.exists():
                continue
            interfaces.append(
                _ProfileInterface(
                    choices_path=choices_path,
                    profile_path=profile_path,
                    provider_path=directory / "provider",
                    source="kernel-platform-profile-class",
                )
            )
        return tuple(interfaces)

    def _acpi_interface(self) -> _ProfileInterface | None:
        choices_path = self.acpi_root / "platform_profile_choices"
        profile_path = self.acpi_root / "platform_profile"
        if not choices_path.exists() and not profile_path.exists():
            return None
        return _ProfileInterface(
            choices_path=choices_path,
            profile_path=profile_path,
            provider_path=None,
            source="kernel-platform-profile-acpi",
        )

    def _interface_candidates(self) -> tuple[_ProfileInterface, ...]:
        candidates = list(self._class_interfaces())
        acpi_interface = self._acpi_interface()
        if acpi_interface is not None:
            candidates.append(acpi_interface)
        return tuple(candidates)

    def _select_interface(self) -> _ProfileInterface | None:
        for interface in self._interface_candidates():
            if _read_text(interface.profile_path) is not None:
                return interface
            if _read_text(interface.choices_path) is not None:
                return interface
        return None

    def read_capabilities(self) -> ThermalCapabilities:
        interface = self._select_interface()
        if interface is None:
            return ThermalCapabilities()

        supported_profiles = list(_parse_profiles(_read_text(interface.choices_path)))
        current_profile = _profile_from_token(_read_text(interface.profile_path))
        if current_profile is not None and current_profile not in supported_profiles:
            supported_profiles.append(current_profile)

        available = bool(supported_profiles or current_profile is not None)
        provider = _read_text(interface.provider_path)
        if available and provider is None:
            provider = "kernel-platform-profile"

        return ThermalCapabilities(
            available=available,
            provider=provider,
            supported_profiles=tuple(supported_profiles),
            writable=interface.profile_path.exists()
            and os.access(interface.profile_path, os.W_OK),
        )

    def read_temperatures(self) -> dict[str, float]:
        try:
            thermal_zones = sorted(
                (
                    path
                    for path in self.thermal_root.iterdir()
                    if path.is_dir() and path.name.startswith("thermal_zone")
                ),
                key=lambda path: path.name,
            )
        except OSError:
            return {}

        temperatures: dict[str, float] = {}
        for zone in thermal_zones:
            temperature = _temperature_celsius(zone / "temp")
            if temperature is None:
                continue

            label = _read_text(zone / "type") or zone.name
            if label in temperatures:
                label = f"{label} ({zone.name})"
            temperatures[label] = temperature
        return temperatures

    def read_state(self) -> ThermalState:
        interface = self._select_interface()
        current_profile = (
            _profile_from_token(_read_text(interface.profile_path))
            if interface is not None
            else None
        )
        temperatures = self.read_temperatures()

        source: str | None = None
        if interface is not None:
            source = interface.source
        elif temperatures:
            source = "kernel-thermal-zone"

        return ThermalState(
            current_profile=current_profile,
            temperatures_celsius=temperatures or None,
            source=source,
        )


__all__ = ["PlatformProfileReader"]
