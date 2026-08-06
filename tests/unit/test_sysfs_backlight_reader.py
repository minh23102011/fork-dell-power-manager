from pathlib import Path

from powerdeck_backends.desktop.backlight import SysfsBacklightReader


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{value}\n", encoding="utf-8")


def test_reads_display_brightness(tmp_path: Path) -> None:
    backlight_root = tmp_path / "backlight"
    device = backlight_root / "intel_backlight"
    _write(device / "brightness", 1000)
    _write(device / "actual_brightness", 900)
    _write(device / "max_brightness", 1800)
    _write(device / "type", "raw")

    devices = SysfsBacklightReader(
        backlight_root=backlight_root,
        leds_root=tmp_path / "leds",
    ).read_brightness_devices()

    assert len(devices) == 1
    assert devices[0].name == "intel_backlight"
    assert devices[0].device_class == "raw"
    assert devices[0].current == 900
    assert devices[0].maximum == 1800
    assert devices[0].current_percent == 50.0



def test_zero_actual_brightness_is_preserved(tmp_path: Path) -> None:
    backlight_root = tmp_path / "backlight"
    device = backlight_root / "intel_backlight"
    _write(device / "brightness", 20)
    _write(device / "actual_brightness", 0)
    _write(device / "max_brightness", 100)

    device_state = SysfsBacklightReader(
        backlight_root=backlight_root,
        leds_root=tmp_path / "leds",
    ).read_brightness_devices()[0]

    assert device_state.current == 0
    assert device_state.current_percent == 0.0

def test_brightness_falls_back_to_requested_value(tmp_path: Path) -> None:
    backlight_root = tmp_path / "backlight"
    device = backlight_root / "amdgpu_bl1"
    _write(device / "brightness", 40)
    _write(device / "max_brightness", 100)

    devices = SysfsBacklightReader(
        backlight_root=backlight_root,
        leds_root=tmp_path / "leds",
    ).read_brightness_devices()

    assert devices[0].current == 40
    assert devices[0].current_percent == 40.0


def test_reads_keyboard_backlight_levels(tmp_path: Path) -> None:
    leds_root = tmp_path / "leds"
    keyboard = leds_root / "dell::kbd_backlight"
    _write(keyboard / "brightness", 1)
    _write(keyboard / "max_brightness", 2)
    _write(leds_root / "input3::capslock" / "brightness", 0)
    _write(leds_root / "input3::capslock" / "max_brightness", 1)

    devices = SysfsBacklightReader(
        backlight_root=tmp_path / "backlight",
        leds_root=leds_root,
    ).read_keyboard_backlights()

    assert len(devices) == 1
    assert devices[0].name == "dell::kbd_backlight"
    assert devices[0].current_level == 1
    assert devices[0].maximum_level == 2
    assert devices[0].available_levels == (0, 1, 2)


def test_large_keyboard_range_is_not_eagerly_enumerated(
    tmp_path: Path,
) -> None:
    leds_root = tmp_path / "leds"
    keyboard = leds_root / "vendor::keyboard_backlight"
    _write(keyboard / "brightness", 64)
    _write(keyboard / "max_brightness", 255)

    device = SysfsBacklightReader(
        backlight_root=tmp_path / "backlight",
        leds_root=leds_root,
    ).read_keyboard_backlights()[0]

    assert device.maximum_level == 255
    assert device.available_levels == ()


def test_missing_or_malformed_sysfs_is_safe(tmp_path: Path) -> None:
    backlight_root = tmp_path / "backlight"
    device = backlight_root / "broken"
    _write(device / "brightness", "not-a-number")
    _write(device / "max_brightness", 0)

    reader = SysfsBacklightReader(
        backlight_root=backlight_root,
        leds_root=tmp_path / "missing-leds",
    )

    brightness = reader.read_brightness_devices()

    assert brightness[0].current is None
    assert brightness[0].current_percent is None
    assert reader.read_keyboard_backlights() == ()
