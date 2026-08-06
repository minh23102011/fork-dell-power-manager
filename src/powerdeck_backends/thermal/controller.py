"""Safe apply, verify, and rollback for Linux platform profiles."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from powerdeck_core.errors import (
    CommandExecutionError,
    MissingCapabilityError,
    PermissionDeniedError,
    RollbackError,
    StateVerificationError,
)
from powerdeck_core.models import SerializableModel, ThermalProfile
from powerdeck_core.validation import validate_thermal_profile

_DEFAULT_PLATFORM_PROFILE_ROOT = Path("/sys/class/platform-profile")
_DEFAULT_ACPI_ROOT = Path("/sys/firmware/acpi")

type ReadText = Callable[[Path], str | None]
type WriteText = Callable[[Path, str], None]


@dataclass(frozen=True, slots=True)
class ThermalControlStatus(SerializableModel):
    """Current writable platform-profile state."""

    current_profile: ThermalProfile | None
    available_profiles: tuple[ThermalProfile, ...]
    source: str | None
    profile_path: str | None


@dataclass(frozen=True, slots=True)
class ThermalProfileApplyResult(SerializableModel):
    """Verified result of one thermal profile apply operation."""

    requested_profile: ThermalProfile
    previous_profile: ThermalProfile
    current_profile: ThermalProfile
    changed: bool
    verified: bool
    source: str
    profile_path: str


@dataclass(frozen=True, slots=True)
class _ProfileInterface:
    choices_path: Path
    profile_path: Path
    source: str


def _read_text(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    return value or None


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


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


class PlatformProfileController:
    """Change one kernel platform profile transactionally."""

    def __init__(
        self,
        platform_profile_root: Path = _DEFAULT_PLATFORM_PROFILE_ROOT,
        acpi_root: Path = _DEFAULT_ACPI_ROOT,
        *,
        read_text: ReadText | None = None,
        write_text: WriteText | None = None,
    ) -> None:
        self.platform_profile_root = platform_profile_root
        self.acpi_root = acpi_root
        self._read_text: ReadText = read_text or _read_text
        self._write_text: WriteText = write_text or _write_text

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
            profile_path = directory / "profile"
            choices_path = directory / "choices"
            if not profile_path.exists() and not choices_path.exists():
                continue
            interfaces.append(
                _ProfileInterface(
                    choices_path=choices_path,
                    profile_path=profile_path,
                    source="kernel-platform-profile-class",
                )
            )
        return tuple(interfaces)

    def _acpi_interface(self) -> _ProfileInterface | None:
        profile_path = self.acpi_root / "platform_profile"
        choices_path = self.acpi_root / "platform_profile_choices"
        if not profile_path.exists() and not choices_path.exists():
            return None
        return _ProfileInterface(
            choices_path=choices_path,
            profile_path=profile_path,
            source="kernel-platform-profile-acpi",
        )

    def _interfaces(self) -> tuple[_ProfileInterface, ...]:
        interfaces = list(self._class_interfaces())
        acpi = self._acpi_interface()
        if acpi is not None:
            interfaces.append(acpi)
        return tuple(interfaces)

    def _select_interface(self) -> _ProfileInterface | None:
        for interface in self._interfaces():
            if self._read_text(interface.profile_path) is not None:
                return interface
            if self._read_text(interface.choices_path) is not None:
                return interface
        return None

    def read_status(self) -> ThermalControlStatus:
        """Read current state without changing the machine."""

        interface = self._select_interface()
        if interface is None:
            return ThermalControlStatus(
                current_profile=None,
                available_profiles=(),
                source=None,
                profile_path=None,
            )

        available = _parse_profiles(self._read_text(interface.choices_path))
        current = _profile_from_token(self._read_text(interface.profile_path))
        if current is not None and current not in available:
            available = (*available, current)

        return ThermalControlStatus(
            current_profile=current,
            available_profiles=available,
            source=interface.source,
            profile_path=str(interface.profile_path),
        )

    def _require_interface(self) -> _ProfileInterface:
        interface = self._select_interface()
        if interface is None:
            raise MissingCapabilityError(
                "No kernel platform-profile interface was found.",
                component="thermal",
            )
        return interface

    def _write_profile(
        self,
        interface: _ProfileInterface,
        profile: ThermalProfile,
    ) -> None:
        try:
            self._write_text(
                interface.profile_path,
                f"{profile.value}\n",
            )
        except PermissionError as error:
            raise PermissionDeniedError(
                "Permission denied while writing the thermal profile.",
                component="thermal",
                hint=(
                    "Run the privileged helper through PowerDeck's "
                    "authorization path."
                ),
                details={
                    "path": str(interface.profile_path),
                    "profile": profile.value,
                },
            ) from error
        except OSError as error:
            raise CommandExecutionError(
                "The kernel thermal profile could not be written.",
                component="thermal",
                details={
                    "path": str(interface.profile_path),
                    "profile": profile.value,
                    "reason": str(error),
                },
            ) from error

    def apply(
        self,
        value: str | ThermalProfile,
    ) -> ThermalProfileApplyResult:
        """Validate, snapshot, apply, verify, and rollback on failure."""

        interface = self._require_interface()
        available = _parse_profiles(
            self._read_text(interface.choices_path)
        )
        if not available:
            raise MissingCapabilityError(
                "The platform-profile choices list is unavailable.",
                component="thermal",
                details={"path": str(interface.choices_path)},
            )

        requested = validate_thermal_profile(value, available)
        previous = _profile_from_token(
            self._read_text(interface.profile_path)
        )
        if previous is None:
            raise MissingCapabilityError(
                "The current thermal profile could not be read safely.",
                component="thermal",
                details={"path": str(interface.profile_path)},
            )

        if requested is previous:
            return ThermalProfileApplyResult(
                requested_profile=requested,
                previous_profile=previous,
                current_profile=previous,
                changed=False,
                verified=True,
                source=interface.source,
                profile_path=str(interface.profile_path),
            )

        self._write_profile(interface, requested)
        observed = _profile_from_token(
            self._read_text(interface.profile_path)
        )
        if observed is requested:
            return ThermalProfileApplyResult(
                requested_profile=requested,
                previous_profile=previous,
                current_profile=observed,
                changed=True,
                verified=True,
                source=interface.source,
                profile_path=str(interface.profile_path),
            )

        self._write_profile(interface, previous)
        restored = _profile_from_token(
            self._read_text(interface.profile_path)
        )
        if restored is not previous:
            raise RollbackError(
                "Thermal profile verification failed and rollback did not restore the previous profile.",
                component="thermal",
                details={
                    "requested": requested.value,
                    "previous": previous.value,
                    "observed_after_apply": (
                        None if observed is None else observed.value
                    ),
                    "observed_after_rollback": (
                        None if restored is None else restored.value
                    ),
                    "path": str(interface.profile_path),
                },
            )

        raise StateVerificationError(
            "Thermal profile verification failed; the previous profile was restored.",
            component="thermal",
            details={
                "requested": requested.value,
                "previous": previous.value,
                "observed": (
                    None if observed is None else observed.value
                ),
                "rollback_verified": True,
                "path": str(interface.profile_path),
            },
        )


__all__ = [
    "PlatformProfileController",
    "ThermalControlStatus",
    "ThermalProfileApplyResult",
]
