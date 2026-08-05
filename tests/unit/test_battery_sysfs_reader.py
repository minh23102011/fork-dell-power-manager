from pathlib import Path

from powerdeck_backends.battery.sysfs_reader import SysfsBatteryReader
from powerdeck_core.models import ChargeMode


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{value}\n", encoding="utf-8")


def _make_dell_battery(root: Path, name: str = "BAT0") -> Path:
    battery = root / name
    battery.mkdir(parents=True)
    values = {
        "present": 1,
        "status": "Not charging",
        "capacity": 79,
        "capacity_level": "Normal",
        "technology": "Li-ion",
        "manufacturer": "BYD",
        "model_name": "DELL",
        "cycle_count": 42,
        "energy_now": 42_000_000,
        "energy_full": 50_000_000,
        "energy_full_design": 55_000_000,
        "charge_now": 3_100_000,
        "charge_full": 3_700_000,
        "charge_full_design": 4_000_000,
        "power_now": 6_800_000,
        "current_now": 610_000,
        "voltage_now": 11_400_000,
        "temp": 319,
        "charge_types": "Trickle Fast Standard Adaptive [Custom]",
        "charge_control_start_threshold": 50,
        "charge_control_end_threshold": 80,
    }
    for key, value in values.items():
        _write(battery / key, value)
    return battery


def test_reads_battery_values_and_converts_kernel_units(tmp_path: Path) -> None:
    root = tmp_path / "power_supply"
    _make_dell_battery(root)

    batteries = SysfsBatteryReader(root).read_batteries()

    assert len(batteries) == 1
    battery = batteries[0]
    assert battery.name == "BAT0"
    assert battery.present is True
    assert battery.capacity_percent == 79
    assert battery.energy_now_wh == 42.0
    assert battery.charge_now_ah == 3.1
    assert battery.power_now_w == 6.8
    assert battery.current_now_a == 0.61
    assert battery.voltage_now_v == 11.4
    assert battery.temperature_celsius == 31.9
    assert battery.active_charge_type == "Custom"
    assert battery.charge_types == ("Trickle", "Fast", "Standard", "Adaptive", "Custom")
    assert battery.charge_control_start_percent == 50
    assert battery.charge_control_end_percent == 80


def test_reads_charge_capabilities_and_maps_fast_to_express(tmp_path: Path) -> None:
    root = tmp_path / "power_supply"
    _make_dell_battery(root)

    capabilities = SysfsBatteryReader(root).read_charge_capabilities()

    assert capabilities.available is True
    assert capabilities.provider == "kernel-power-supply"
    assert capabilities.custom_thresholds is True
    assert capabilities.supported_modes == (
        ChargeMode.ADAPTIVE,
        ChargeMode.STANDARD,
        ChargeMode.EXPRESS,
        ChargeMode.CUSTOM,
    )


def test_reads_current_charge_state_and_interval(tmp_path: Path) -> None:
    root = tmp_path / "power_supply"
    _make_dell_battery(root)

    state = SysfsBatteryReader(root).read_charge_state()

    assert state.battery_name == "BAT0"
    assert state.mode is ChargeMode.CUSTOM
    assert state.interval is not None
    assert state.interval.start_percent == 50
    assert state.interval.end_percent == 80
    assert state.source == "kernel-power-supply"


def test_missing_and_malformed_values_are_tolerated(tmp_path: Path) -> None:
    root = tmp_path / "power_supply"
    battery = root / "BAT0"
    battery.mkdir(parents=True)
    _write(battery / "capacity", "not-a-number")
    _write(battery / "present", 4)
    _write(battery / "status", "Discharging")

    result = SysfsBatteryReader(root).read_batteries()[0]

    assert result.capacity_percent is None
    assert result.present is None
    assert result.status == "Discharging"
    assert result.power_now_w is None


def test_multiple_batteries_are_sorted_by_name(tmp_path: Path) -> None:
    root = tmp_path / "power_supply"
    _make_dell_battery(root, "BAT1")
    _make_dell_battery(root, "BAT0")

    batteries = SysfsBatteryReader(root).read_batteries()

    assert tuple(battery.name for battery in batteries) == ("BAT0", "BAT1")


def test_missing_power_supply_root_returns_empty_state(tmp_path: Path) -> None:
    reader = SysfsBatteryReader(tmp_path / "missing")

    assert reader.read_batteries() == ()
    assert reader.read_charge_capabilities().available is False
    assert reader.read_charge_state().battery_name is None
