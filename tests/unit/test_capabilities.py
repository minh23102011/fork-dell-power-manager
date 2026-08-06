from powerdeck_core.capabilities import (
    build_diagnostics,
    find_battery_refresh_mode,
    select_internal_output,
)
from powerdeck_core.models import (
    BrightnessDevice,
    ChargeCapabilities,
    DisplayMode,
    DisplayOutput,
    PowerDeckCapabilities,
    PowerManagerState,
    ServiceActivity,
    ServiceState,
    ThermalCapabilities,
)


def _output() -> DisplayOutput:
    return DisplayOutput(
        connector="eDP-1",
        internal=True,
        modes=(
            DisplayMode(
                1920,
                1080,
                120.003,
                current=True,
                preferred=True,
            ),
            DisplayMode(1920, 1080, 60.012),
            DisplayMode(1280, 720, 60.0),
        ),
    )


def _base_capabilities(
    power_manager: PowerManagerState | None = None,
) -> PowerDeckCapabilities:
    return PowerDeckCapabilities(
        charge=ChargeCapabilities(available=True),
        thermal=ThermalCapabilities(available=True),
        power_manager=(
            power_manager
            if power_manager is not None
            else PowerManagerState()
        ),
        displays=(_output(),),
        brightness_devices=(
            BrightnessDevice(
                "intel_backlight",
                "backlight",
            ),
        ),
        audio_control=True,
        ac_monitoring=True,
    )


def test_internal_output_and_same_resolution_60hz_selection() -> None:
    output = _output()
    assert select_internal_output((output,)) is output
    mode = find_battery_refresh_mode(output)
    assert mode is not None
    assert mode.width == 1920
    assert mode.refresh_hz == 60.012


def test_refresh_selection_uses_preferred_mode_when_current_unknown() -> None:
    output = DisplayOutput(
        connector="eDP-1",
        internal=True,
        modes=(
            DisplayMode(
                1920,
                1080,
                120.003,
                preferred=True,
            ),
            DisplayMode(1920, 1080, 60.012),
            DisplayMode(1280, 720, 60.0),
        ),
    )

    mode = find_battery_refresh_mode(output)

    assert mode is not None
    assert mode.width == 1920
    assert mode.height == 1080
    assert mode.refresh_hz == 60.012


def test_refresh_selection_requires_reference_mode() -> None:
    output = DisplayOutput(
        connector="eDP-1",
        internal=True,
        modes=(
            DisplayMode(1920, 1080, 60.012),
            DisplayMode(1280, 720, 60.0),
        ),
    )

    assert find_battery_refresh_mode(output) is None


def test_diagnostics_reports_power_manager_conflict() -> None:
    power_manager = PowerManagerState(
        services=(
            ServiceState(
                "power-profiles-daemon",
                ServiceActivity.ACTIVE,
            ),
            ServiceState(
                "tlp",
                ServiceActivity.ACTIVE,
            ),
        )
    )

    issues = build_diagnostics(
        _base_capabilities(power_manager)
    )

    assert any(
        issue.code == "power-manager-conflict"
        for issue in issues
    )


def test_diagnostics_reports_profile_query_failure() -> None:
    power_manager = PowerManagerState(
        services=(
            ServiceState(
                "power-profiles-daemon",
                ServiceActivity.ACTIVE,
                details="powerprofilesctl failed",
            ),
        ),
        provider="power-profiles-daemon",
    )

    issues = build_diagnostics(
        _base_capabilities(power_manager)
    )

    issue = next(
        item
        for item in issues
        if item.code == "power-profile-query-failed"
    )
    assert issue.severity.value == "warning"
    assert issue.details == {
        "reason": "powerprofilesctl failed"
    }
