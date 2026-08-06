from pathlib import Path

from powerdeck_backends.battery.controller import SysfsChargeController
from powerdeck_core.models import ChargeInterval, ChargeMode


def _battery(tmp_path: Path) -> Path:
    battery = tmp_path / "BAT0"
    battery.mkdir()
    (battery / "type").write_text("Battery\n", encoding="utf-8")
    (battery / "charge_types").write_text(
        "Adaptive Standard Express Primarily_AC Custom\n",
        encoding="utf-8",
    )
    (battery / "charge_type").write_text(
        "Custom\n",
        encoding="utf-8",
    )
    (battery / "charge_control_start_threshold").write_text(
        "50\n",
        encoding="utf-8",
    )
    (battery / "charge_control_end_threshold").write_text(
        "80\n",
        encoding="utf-8",
    )
    return battery


def test_reads_charge_state(tmp_path: Path) -> None:
    _battery(tmp_path)
    status = SysfsChargeController(tmp_path).read_status()

    assert status.current_mode is ChargeMode.CUSTOM
    assert status.interval == ChargeInterval(50, 80)
    assert ChargeMode.EXPRESS in status.available_modes


def test_applies_mode(tmp_path: Path) -> None:
    battery = _battery(tmp_path)
    controller = SysfsChargeController(tmp_path)

    result = controller.apply_mode("standard")

    assert result.verified is True
    assert result.current_mode is ChargeMode.STANDARD
    assert (
        battery / "charge_type"
    ).read_text(encoding="utf-8").strip() == "Standard"


def test_applies_custom_thresholds(tmp_path: Path) -> None:
    battery = _battery(tmp_path)
    controller = SysfsChargeController(tmp_path)

    result = controller.apply_custom(55, 85)

    assert result.current_interval == ChargeInterval(55, 85)
    assert (
        battery / "charge_control_start_threshold"
    ).read_text(encoding="utf-8").strip() == "55"
    assert (
        battery / "charge_control_end_threshold"
    ).read_text(encoding="utf-8").strip() == "85"
