from pathlib import Path

from powerdeck_backends.telemetry.hwmon import HwmonFanReader


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def test_hwmon_fan_reader_reads_rpm_and_label(tmp_path: Path) -> None:
    hwmon = tmp_path / "hwmon0"
    _write(hwmon / "name", "dell_smm")
    _write(hwmon / "fan1_label", "CPU fan")
    _write(hwmon / "fan1_input", "2780")

    readings = HwmonFanReader(tmp_path)

    assert len(readings.read()) == 1
    fan = readings.read()[0]
    assert fan.label == "CPU fan"
    assert fan.rpm == 2780


def test_hwmon_backend_contains_no_pwm_write_path() -> None:
    module = Path(
        "src/powerdeck_backends/telemetry/hwmon.py"
    ).read_text(encoding="utf-8")

    assert "write_text" not in module
    assert "pwm" in module
