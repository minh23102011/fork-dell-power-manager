from powerdeck_core.models import (
    BatteryInfo,
    ChargeInterval,
    ChargeMode,
    ChargeState,
    DisplayMode,
    DisplayOutput,
    PowerDeckStatus,
)


def test_nested_models_serialize_predictably() -> None:
    status = PowerDeckStatus(
        batteries=(BatteryInfo(name="BAT0", capacity_percent=79),),
        charge=ChargeState(
            battery_name="BAT0",
            mode=ChargeMode.CUSTOM,
            interval=ChargeInterval(50, 80),
        ),
    )

    payload = status.to_dict()

    assert payload["schema_version"] == 1
    assert payload["batteries"][0]["capacity_percent"] == 79
    assert payload["charge"]["mode"] == "custom"
    assert payload["charge"]["interval"] == {
        "start_percent": 50,
        "end_percent": 80,
    }


def test_battery_health_prefers_energy_capacity() -> None:
    battery = BatteryInfo(
        name="BAT0",
        energy_full_wh=45.0,
        energy_full_design_wh=50.0,
        charge_full_ah=3.0,
        charge_full_design_ah=3.0,
    )

    assert battery.health_percent == 90.0


def test_display_current_mode() -> None:
    output = DisplayOutput(
        connector="eDP-1",
        internal=True,
        modes=(
            DisplayMode(1920, 1080, 120.003, current=True, preferred=True),
            DisplayMode(1920, 1080, 60.012),
        ),
    )

    assert output.current_mode is not None
    assert output.current_mode.refresh_hz == 120.003
