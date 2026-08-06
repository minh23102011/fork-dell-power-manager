"""Pure presentation models for the standalone PowerDeck application."""

from __future__ import annotations

from dataclasses import dataclass

from powerdeck_backends.scanner import DiscoverySnapshot
from powerdeck_core.capabilities import select_internal_output
from powerdeck_core.models import AudioState, DisplayMode


@dataclass(frozen=True, slots=True)
class RowModel:
    """One label/value row rendered by the GTK frontend."""

    label: str
    value: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class PageModel:
    """One top-level page in the PowerDeck window."""

    name: str
    title: str
    description: str
    groups: tuple[tuple[str, tuple[RowModel, ...]], ...]


@dataclass(frozen=True, slots=True)
class DashboardModel:
    """Complete read-only application state."""

    battery: PageModel
    thermal: PageModel
    saver: PageModel
    diagnostics: tuple[str, ...]


def _text(value: object | None) -> str:
    return "Unknown" if value is None else str(value)


def _percent(value: float | int | None, *, digits: int = 0) -> str:
    if value is None:
        return "Unknown"
    return f"{value:.{digits}f}%"


def _on_ac(value: bool | None) -> str:
    if value is None:
        return "Unknown"
    return "Connected" if value else "Disconnected"


def _mode_label(mode: DisplayMode | None) -> str:
    if mode is None:
        return "Unknown"
    return f"{mode.width} x {mode.height} @ {mode.refresh_hz:.3f} Hz"


def _audio_label(audio: AudioState) -> str:
    if not audio.available:
        return "Unavailable"

    sink = _percent(
        None if audio.sink_volume is None else audio.sink_volume * 100,
    )
    mute = (
        "mute unknown"
        if audio.sink_muted is None
        else ("muted" if audio.sink_muted else "unmuted")
    )
    return f"{sink}, {mute}"


def _battery_page(snapshot: DiscoverySnapshot) -> PageModel:
    status = snapshot.status
    battery = status.batteries[0] if status.batteries else None
    interval = status.charge.interval

    battery_rows = (
        RowModel(
            "Battery",
            "Not detected"
            if battery is None
            else f"{battery.name} — {_percent(battery.capacity_percent)}",
        ),
        RowModel(
            "State",
            "Unknown" if battery is None else _text(battery.status),
        ),
        RowModel(
            "Health",
            "Unknown"
            if battery is None
            else _percent(battery.health_percent, digits=1),
        ),
        RowModel(
            "Cycle count",
            "Unknown"
            if battery is None
            else _text(battery.cycle_count),
        ),
        RowModel("AC adapter", _on_ac(status.on_ac_power)),
    )

    charging_rows = (
        RowModel(
            "Charging mode",
            (
                "Unknown"
                if status.charge.mode is None
                else status.charge.mode.value
            ),
        ),
        RowModel(
            "Custom interval",
            (
                "Unknown"
                if interval is None
                else (
                    f"{interval.start_percent}% → "
                    f"{interval.end_percent}%"
                )
            ),
        ),
        RowModel(
            "Write access",
            (
                "Read-only in this build"
                if not snapshot.capabilities.charge.writable
                else "Available to current process"
            ),
            (
                "The local app intentionally does not change firmware "
                "settings yet."
            ),
        ),
    )

    return PageModel(
        name="battery",
        title="Battery",
        description="Battery condition and Dell charging configuration.",
        groups=(
            ("Status", battery_rows),
            ("Charging", charging_rows),
        ),
    )


def _thermal_page(snapshot: DiscoverySnapshot) -> PageModel:
    status = snapshot.status
    capabilities = snapshot.capabilities
    supported = capabilities.thermal.supported_profiles
    temperatures = status.thermal.temperatures_celsius or {}

    profile_rows = (
        RowModel(
            "Current thermal mode",
            (
                "Unknown"
                if status.thermal.current_profile is None
                else status.thermal.current_profile.value
            ),
        ),
        RowModel(
            "Supported modes",
            (
                "None detected"
                if not supported
                else ", ".join(profile.value for profile in supported)
            ),
        ),
        RowModel(
            "OS power profile",
            _text(status.power_manager.current_profile),
        ),
        RowModel(
            "CPU governor",
            _text(capabilities.cpu.current_governor),
        ),
    )

    temperature_rows = tuple(
        RowModel(label, f"{temperature:.1f} °C")
        for label, temperature in sorted(temperatures.items())
    )
    if not temperature_rows:
        temperature_rows = (
            RowModel("Sensors", "No temperatures reported"),
        )

    return PageModel(
        name="thermal",
        title="Thermal Mode",
        description="Platform profile, CPU policy, and temperature sensors.",
        groups=(
            ("Profiles", profile_rows),
            ("Temperatures", temperature_rows),
        ),
    )


def _saver_page(snapshot: DiscoverySnapshot) -> PageModel:
    status = snapshot.status
    capabilities = snapshot.capabilities
    display = select_internal_output(status.displays)
    display_mode = None if display is None else display.current_mode
    brightness = (
        capabilities.brightness_devices[0]
        if capabilities.brightness_devices
        else None
    )
    keyboard = (
        capabilities.keyboard_backlights[0]
        if capabilities.keyboard_backlights
        else None
    )

    readiness_rows = (
        RowModel(
            "Battery Saver",
            "Preview only",
            (
                "Automatic apply and restore will be enabled after the "
                "session agent and privileged daemon are connected."
            ),
        ),
        RowModel("AC trigger", _on_ac(status.on_ac_power)),
        RowModel(
            "Power profile",
            _text(status.power_manager.current_profile),
        ),
        RowModel(
            "Thermal mode",
            (
                "Unknown"
                if status.thermal.current_profile is None
                else status.thermal.current_profile.value
            ),
        ),
    )

    device_rows = (
        RowModel(
            "Internal display",
            (
                "Not detected"
                if display is None
                else f"{display.connector}: {_mode_label(display_mode)}"
            ),
        ),
        RowModel(
            "Brightness",
            (
                "Unavailable"
                if brightness is None
                else _percent(brightness.current_percent, digits=1)
            ),
        ),
        RowModel(
            "Keyboard backlight",
            (
                "Unavailable"
                if keyboard is None
                else (
                    f"Level {_text(keyboard.current_level)} / "
                    f"{_text(keyboard.maximum_level)}"
                )
            ),
        ),
        RowModel("Audio output", _audio_label(status.audio)),
    )

    return PageModel(
        name="saver",
        title="Battery Saver",
        description=(
            "A read-only preview of the values PowerDeck will coordinate "
            "when running on battery."
        ),
        groups=(
            ("Readiness", readiness_rows),
            ("Session devices", device_rows),
        ),
    )


def build_dashboard(snapshot: DiscoverySnapshot) -> DashboardModel:
    """Convert a discovery snapshot into stable frontend data."""

    diagnostics = tuple(
        f"{issue.severity.value}: {issue.message}"
        for issue in snapshot.status.diagnostics
    )
    return DashboardModel(
        battery=_battery_page(snapshot),
        thermal=_thermal_page(snapshot),
        saver=_saver_page(snapshot),
        diagnostics=diagnostics,
    )


__all__ = [
    "DashboardModel",
    "PageModel",
    "RowModel",
    "build_dashboard",
]
