from dataclasses import replace
from pathlib import Path

from powerdeck_core.config import (
    PowerDeckConfig,
    dumps_config,
    load_config,
    save_config_atomic,
)
from powerdeck_core.models import ChargeMode


def test_default_config_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    original = PowerDeckConfig()

    save_config_atomic(original, path)
    loaded = load_config(path)

    assert loaded.issues == ()
    assert loaded.config == original
    assert "[battery_saver.display]" in path.read_text(encoding="utf-8")


def test_invalid_field_falls_back_without_discarding_whole_config(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """
schema_version = 1

[battery]
preferred_mode = "adaptive"
custom_start = 10
custom_end = 80
unknown_vendor_key = "preserve-me"

[thermal]
preferred_mode = "balanced"
""".strip(),
        encoding="utf-8",
    )

    result = load_config(path)

    assert result.config.battery.preferred_mode is ChargeMode.ADAPTIVE
    assert result.config.battery.custom_start == 50
    assert result.config.battery.extra["unknown_vendor_key"] == "preserve-me"
    assert result.issues


def test_save_creates_backup(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    save_config_atomic(PowerDeckConfig(), path)
    modified = replace(
        PowerDeckConfig(),
        battery=replace(PowerDeckConfig().battery, preferred_mode=ChargeMode.ADAPTIVE),
    )

    save_config_atomic(modified, path)

    assert path.with_suffix(".toml.bak").exists()
    assert load_config(path).config.battery.preferred_mode is ChargeMode.ADAPTIVE


def test_dump_is_deterministic() -> None:
    assert dumps_config(PowerDeckConfig()) == dumps_config(PowerDeckConfig())
