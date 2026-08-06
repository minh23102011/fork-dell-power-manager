from pathlib import Path

from powerdeck_agent.settings import (
    SaverSettings,
    load_settings,
    save_settings,
    settings_from_mapping,
)


def test_invalid_values_fall_back_or_clamp() -> None:
    settings = settings_from_mapping(
        {
            "enabled": "yes",
            "brightness_cap_percent": 150,
            "max_performance_percent": 0,
        }
    )

    assert settings.enabled is True
    assert settings.brightness_cap_percent == 100
    assert settings.max_performance_percent == 1


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "saver.json"
    expected = SaverSettings(
        brightness_cap_percent=35,
        mute_audio=True,
    )

    save_settings(expected, path)

    assert load_settings(path) == expected
