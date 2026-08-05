"""Pure capability-selection and diagnostic rules."""

from __future__ import annotations

from collections.abc import Iterable

from powerdeck_core.models import (
    DiagnosticIssue,
    DisplayMode,
    DisplayOutput,
    PowerDeckCapabilities,
    PowerDeckStatus,
    ServiceActivity,
    Severity,
)


def select_internal_output(outputs: Iterable[DisplayOutput]) -> DisplayOutput | None:
    """Select the internal panel without permanently hardcoding a connector name."""

    materialized = tuple(outputs)
    explicit = next((output for output in materialized if output.internal and output.enabled), None)
    if explicit is not None:
        return explicit
    return next(
        (
            output
            for output in materialized
            if output.enabled and output.connector.lower().startswith(("edp", "lvds", "dsi"))
        ),
        None,
    )


def find_battery_refresh_mode(
    output: DisplayOutput,
    *,
    target_hz: float = 60.0,
    tolerance_hz: float = 1.0,
) -> DisplayMode | None:
    """Find the closest same-resolution mode around the requested refresh rate."""

    reference = output.current_mode
    if reference is None:
        reference = next((mode for mode in output.modes if mode.preferred), None)
    if reference is None:
        return None

    candidates = [
        mode
        for mode in output.modes
        if mode.width == reference.width
        and mode.height == reference.height
        and abs(mode.refresh_hz - target_hz) <= tolerance_hz
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda mode: abs(mode.refresh_hz - target_hz))


def build_diagnostics(
    capabilities: PowerDeckCapabilities,
    status: PowerDeckStatus | None = None,
) -> tuple[DiagnosticIssue, ...]:
    """Create user-facing issues without performing any probing or mutation."""

    issues: list[DiagnosticIssue] = []

    if status is not None and not status.batteries:
        issues.append(
            DiagnosticIssue(
                code="battery-not-found",
                severity=Severity.WARNING,
                component="battery",
                message="No battery device was detected.",
                hint="PowerDeck battery features will remain unavailable on this system.",
            )
        )

    if not capabilities.charge.available:
        issues.append(
            DiagnosticIssue(
                code="charging-control-unavailable",
                severity=Severity.WARNING,
                component="battery",
                message="Battery charging controls are unavailable.",
                hint="Install the vendor backend or check whether firmware exposes charge controls.",
            )
        )

    if not capabilities.thermal.available:
        issues.append(
            DiagnosticIssue(
                code="thermal-profile-unavailable",
                severity=Severity.WARNING,
                component="thermal",
                message="No platform thermal profile interface was detected.",
                hint="Check the platform-profile kernel driver for this laptop.",
            )
        )

    if capabilities.power_manager.has_conflict:
        names = [service.name for service in capabilities.power_manager.active_services]
        issues.append(
            DiagnosticIssue(
                code="power-manager-conflict",
                severity=Severity.ERROR,
                component="power",
                message="Multiple power managers are active and may overwrite each other.",
                hint="Keep only one system power manager active.",
                details={"active_services": names},
            )
        )

    internal = select_internal_output(capabilities.displays)
    if internal is None:
        issues.append(
            DiagnosticIssue(
                code="internal-display-not-found",
                severity=Severity.INFO,
                component="display",
                message="No internal display was detected.",
                hint="Automatic laptop refresh-rate switching will be disabled.",
            )
        )
    elif find_battery_refresh_mode(internal) is None:
        issues.append(
            DiagnosticIssue(
                code="battery-refresh-mode-not-found",
                severity=Severity.INFO,
                component="display",
                message="No same-resolution 60 Hz display mode was detected.",
                hint="Battery Saver will preserve the current refresh rate.",
            )
        )

    if not capabilities.brightness_devices:
        issues.append(
            DiagnosticIssue(
                code="brightness-control-unavailable",
                severity=Severity.WARNING,
                component="display",
                message="No brightness device was detected.",
            )
        )

    if not capabilities.keyboard_backlights:
        issues.append(
            DiagnosticIssue(
                code="keyboard-backlight-unavailable",
                severity=Severity.INFO,
                component="keyboard",
                message="No keyboard backlight device was detected.",
            )
        )

    if not capabilities.audio_control:
        issues.append(
            DiagnosticIssue(
                code="audio-control-unavailable",
                severity=Severity.INFO,
                component="audio",
                message="Session audio controls are unavailable.",
            )
        )

    if not capabilities.ac_monitoring:
        issues.append(
            DiagnosticIssue(
                code="ac-monitoring-unavailable",
                severity=Severity.ERROR,
                component="battery-saver",
                message="AC adapter state cannot be monitored.",
                hint="Automatic Battery Saver activation cannot operate safely.",
            )
        )

    return tuple(issues)


def active_power_manager_names(capabilities: PowerDeckCapabilities) -> tuple[str, ...]:
    return tuple(
        service.name
        for service in capabilities.power_manager.services
        if service.activity is ServiceActivity.ACTIVE
    )


__all__ = [
    "active_power_manager_names",
    "build_diagnostics",
    "find_battery_refresh_mode",
    "select_internal_output",
]
