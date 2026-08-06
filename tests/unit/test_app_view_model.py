from powerdeck_app.view_model import build_dashboard
from powerdeck_backends.scanner import DiscoverySnapshot
from powerdeck_core.models import (
    AcAdapterState,
    AudioState,
    BatteryInfo,
    BrightnessDevice,
    ChargeCapabilities,
    ChargeInterval,
    ChargeMode,
    ChargeState,
    CpuCapabilities,
    DisplayMode,
    DisplayOutput,
    KeyboardBacklightDevice,
    PowerDeckCapabilities,
    PowerDeckStatus,
    PowerManagerState,
    ThermalCapabilities,
    ThermalProfile,
    ThermalState,
)


def _snapshot() -> DiscoverySnapshot:
    display = DisplayOutput(
        connector="eDP-1",
        internal=True,
        modes=(
            DisplayMode(
                width=1920,
                height=1080,
                refresh_hz=120.003,
                current=True,
            ),
            DisplayMode(
                width=1920,
                height=1080,
                refresh_hz=60.012,
            ),
        ),
    )
    power_manager = PowerManagerState(
        provider="power-profiles-daemon",
        current_profile="power-saver",
        available_profiles=(
            "power-saver",
            "balanced",
            "performance",
        ),
    )
    capabilities = PowerDeckCapabilities(
        charge=ChargeCapabilities(
            available=True,
            supported_modes=(ChargeMode.CUSTOM,),
        ),
        thermal=ThermalCapabilities(
            available=True,
            supported_profiles=(
                ThermalProfile.QUIET,
                ThermalProfile.BALANCED,
            ),
        ),
        cpu=CpuCapabilities(
            current_governor="powersave",
        ),
        power_manager=power_manager,
        displays=(display,),
        brightness_devices=(
            BrightnessDevice(
                name="intel_backlight",
                device_class="raw",
                current_percent=40.0,
            ),
        ),
        keyboard_backlights=(
            KeyboardBacklightDevice(
                name="dell::kbd_backlight",
                current_level=1,
                maximum_level=2,
            ),
        ),
        audio_control=True,
        ac_monitoring=True,
    )
    status = PowerDeckStatus(
        batteries=(
            BatteryInfo(
                name="BAT0",
                capacity_percent=65,
                status="Discharging",
                cycle_count=43,
                serial_number="private-serial",
                charge_full_ah=3.554,
                charge_full_design_ah=3.554,
            ),
        ),
        charge=ChargeState(
            battery_name="BAT0",
            mode=ChargeMode.CUSTOM,
            interval=ChargeInterval(50, 55),
        ),
        thermal=ThermalState(
            current_profile=ThermalProfile.QUIET,
            temperatures_celsius={"TCPU": 55.05},
        ),
        power_manager=power_manager,
        displays=(display,),
        brightness_devices=capabilities.brightness_devices,
        keyboard_backlights=capabilities.keyboard_backlights,
        audio=AudioState(
            available=True,
            sink_volume=0.6,
            sink_muted=False,
            backend="wpctl",
        ),
        ac_adapters=(
            AcAdapterState(name="AC", online=False),
        ),
    )
    return DiscoverySnapshot(
        schema_version=1,
        capabilities=capabilities,
        status=status,
    )


def _values(page_name: str) -> dict[str, str]:
    dashboard = build_dashboard(_snapshot())
    page = getattr(dashboard, page_name)
    return {
        row.label: row.value
        for _group, rows in page.groups
        for row in rows
    }


def test_battery_page_uses_current_hardware_state() -> None:
    values = _values("battery")

    assert values["Battery"] == "BAT0 — 65%"
    assert values["Health"] == "100.0%"
    assert values["Custom interval"] == "50% → 55%"
    assert values["AC adapter"] == "Disconnected"


def test_thermal_page_shows_profiles_and_temperature() -> None:
    values = _values("thermal")

    assert values["Current thermal mode"] == "quiet"
    assert values["OS power profile"] == "power-saver"
    assert values["CPU governor"] == "powersave"
    assert values["TCPU"] == "55.0 °C"


def test_saver_page_is_an_explicit_preview() -> None:
    values = _values("saver")

    assert values["Battery Saver"] == "Preview only"
    assert values["Internal display"] == (
        "eDP-1: 1920 x 1080 @ 120.003 Hz"
    )
    assert values["Brightness"] == "40.0%"
    assert values["Keyboard backlight"] == "Level 1 / 2"
    assert values["Audio output"] == "60%, unmuted"


def test_view_model_does_not_expose_battery_serial() -> None:
    dashboard = build_dashboard(_snapshot())
    rendered = repr(dashboard)

    assert "private-serial" not in rendered
