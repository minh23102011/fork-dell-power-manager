from pathlib import Path

from powerdeck_backends.system.power_supply import SysfsAcAdapterReader


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{value}\n", encoding="utf-8")


def test_reads_ac_adapters_and_ignores_batteries(tmp_path: Path) -> None:
    _write(tmp_path / "AC" / "type", "Mains")
    _write(tmp_path / "AC" / "online", 1)
    _write(tmp_path / "AC" / "manufacturer", "Dell")
    _write(tmp_path / "BAT0" / "type", "Battery")
    _write(tmp_path / "BAT0" / "online", 0)

    adapters = SysfsAcAdapterReader(tmp_path).read()

    assert len(adapters) == 1
    assert adapters[0].name == "AC"
    assert adapters[0].online is True
    assert adapters[0].adapter_type == "Mains"
    assert adapters[0].manufacturer == "Dell"


def test_invalid_online_state_is_unknown(tmp_path: Path) -> None:
    _write(tmp_path / "AC" / "type", "Mains")
    _write(tmp_path / "AC" / "online", 2)

    adapters = SysfsAcAdapterReader(tmp_path).read()

    assert adapters[0].online is None


def test_missing_power_supply_root_returns_empty_tuple(tmp_path: Path) -> None:
    assert SysfsAcAdapterReader(tmp_path / "missing").read() == ()
