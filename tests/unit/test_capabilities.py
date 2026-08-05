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
            DisplayMode(1920, 1080, 120.003, current=True, preferred=True),
            DisplayMode(1920, 1080, 60.012),
            DisplayMode(1280, 720, 60.0),
        ),
    )


def test_internal_output_and_same_resolution_60hz_selection() -> None:
    output = _output()
    assert select_internal_output((output,)) is output
    mode = find_battery_refresh_mode(output)
    assert mode is not None
    assert mode.width == 1920
    assert mode.refresh_hz == 60.012


def test_diagnostics_reports_power_manager_conflict() -> None:
    capabilities = PowerDeckCapabilities(
        charge=ChargeCapabilities(available=True),
        thermal=ThermalCapabilities(available=True),
        power_manager=PowerManagerState(
            services=(
                ServiceState("power-profiles-daemon", ServiceActivity.ACTIVE),
                ServiceState("tlp", ServiceActivity.ACTIVE),
            )
        ),
        displays=(_output(),),
        brightness_devices=(BrightnessDevice("intel_backlight", "backlight"),),
        audio_control=True,
        ac_monitoring=True,
    )

    issues = build_diagnostics(capabilities)

    assert any(issue.code == "power-manager-conflict" for issue in issues)
