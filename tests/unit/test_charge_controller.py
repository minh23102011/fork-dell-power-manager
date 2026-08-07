from pathlib import Path

import pytest

from powerdeck_backends.battery.controller import (
    SysfsChargeController,
)
from powerdeck_core.errors import (
    CommandExecutionError,
    StateVerificationError,
)
from powerdeck_core.models import ChargeInterval, ChargeMode


def _write(path: Path, value: str) -> None:
    path.write_text(f"{value}\n", encoding="utf-8")


def _combined_battery(
    tmp_path: Path,
    *,
    active: str = "Custom",
) -> Path:
    battery = tmp_path / "BAT0"
    battery.mkdir()
    _write(battery / "type", "Battery")
    choices = (
        "Trickle",
        "Fast",
        "Standard",
        "Adaptive",
        "Custom",
    )
    rendered = " ".join(
        (
            f"[{choice}]"
            if choice == active
            else choice
        )
        for choice in choices
    )
    _write(
        battery / "charge_types",
        rendered,
    )
    _write(
        battery / "charge_control_start_threshold",
        "50",
    )
    _write(
        battery / "charge_control_end_threshold",
        "80",
    )
    return battery


class KernelListWriter:
    def __init__(self, choices: tuple[str, ...]) -> None:
        self.choices = choices
        self.writes: list[tuple[str, str]] = []

    def __call__(self, path: Path, value: str) -> None:
        requested = value.strip()
        self.writes.append((path.name, requested))
        if path.name != "charge_types":
            _write(path, requested)
            return
        rendered = " ".join(
            (
                f"[{choice}]"
                if choice == requested
                else choice
            )
            for choice in self.choices
        )
        _write(path, rendered)


def test_reads_active_mode_from_combined_charge_types(
    tmp_path: Path,
) -> None:
    _combined_battery(tmp_path)
    status = SysfsChargeController(tmp_path).read_status()

    assert status.current_mode is ChargeMode.CUSTOM
    assert status.available_modes == (
        ChargeMode.EXPRESS,
        ChargeMode.STANDARD,
        ChargeMode.ADAPTIVE,
        ChargeMode.CUSTOM,
    )
    assert status.interval == ChargeInterval(50, 80)


def test_applies_mode_through_combined_charge_types(
    tmp_path: Path,
) -> None:
    battery = _combined_battery(tmp_path)
    writer = KernelListWriter(
        ("Trickle", "Fast", "Standard", "Adaptive", "Custom")
    )
    controller = SysfsChargeController(
        tmp_path,
        write_text=writer,
    )

    result = controller.apply_mode("standard")

    assert result.verified is True
    assert result.previous_mode is ChargeMode.CUSTOM
    assert result.current_mode is ChargeMode.STANDARD
    assert "[Standard]" in (
        battery / "charge_types"
    ).read_text(encoding="utf-8")


def test_legacy_split_mode_file_remains_supported(
    tmp_path: Path,
) -> None:
    battery = _combined_battery(tmp_path)
    _write(battery / "charge_type", "Custom")
    controller = SysfsChargeController(tmp_path)

    result = controller.apply_mode("adaptive")

    assert result.current_mode is ChargeMode.ADAPTIVE
    assert (
        battery / "charge_type"
    ).read_text(encoding="utf-8").strip() == "Adaptive"


def test_unknown_active_raw_mode_can_still_be_rolled_back(
    tmp_path: Path,
) -> None:
    _combined_battery(tmp_path, active="Trickle")
    writer = KernelListWriter(
        ("Trickle", "Fast", "Standard", "Adaptive", "Custom")
    )
    controller = SysfsChargeController(
        tmp_path,
        write_text=writer,
    )

    result = controller.apply_mode("standard")

    assert result.previous_mode is None
    assert result.current_mode is ChargeMode.STANDARD


def test_applies_custom_mode_and_thresholds(
    tmp_path: Path,
) -> None:
    battery = _combined_battery(tmp_path, active="Standard")
    writer = KernelListWriter(
        ("Trickle", "Fast", "Standard", "Adaptive", "Custom")
    )
    controller = SysfsChargeController(
        tmp_path,
        write_text=writer,
    )

    result = controller.apply_custom(55, 85)

    assert result.current_mode is ChargeMode.CUSTOM
    assert result.current_interval == ChargeInterval(55, 85)
    assert (
        battery / "charge_control_start_threshold"
    ).read_text(encoding="utf-8").strip() == "55"
    assert (
        battery / "charge_control_end_threshold"
    ).read_text(encoding="utf-8").strip() == "85"


def test_verification_failure_restores_exact_raw_mode(
    tmp_path: Path,
) -> None:
    battery = _combined_battery(tmp_path)

    def ignore_standard(path: Path, value: str) -> None:
        requested = value.strip()
        if path.name == "charge_types":
            if requested == "Custom":
                _write(
                    path,
                    "Trickle Fast Standard Adaptive [Custom]",
                )
            return
        _write(path, requested)

    controller = SysfsChargeController(
        tmp_path,
        write_text=ignore_standard,
    )

    with pytest.raises(StateVerificationError):
        controller.apply_mode("standard")

    assert "[Custom]" in (
        battery / "charge_types"
    ).read_text(encoding="utf-8")


def test_partial_custom_failure_rolls_back_mode_and_thresholds(
    tmp_path: Path,
) -> None:
    battery = _combined_battery(tmp_path, active="Standard")
    kernel = KernelListWriter(
        ("Trickle", "Fast", "Standard", "Adaptive", "Custom")
    )
    failed = False

    def fail_first_new_end(path: Path, value: str) -> None:
        nonlocal failed
        requested = value.strip()
        if (
            path.name == "charge_control_end_threshold"
            and requested == "85"
            and not failed
        ):
            failed = True
            raise OSError("simulated firmware rejection")
        kernel(path, value)

    controller = SysfsChargeController(
        tmp_path,
        write_text=fail_first_new_end,
    )

    with pytest.raises(CommandExecutionError):
        controller.apply_custom(55, 85)

    status = controller.read_status()
    assert status.current_mode is ChargeMode.STANDARD
    assert status.interval == ChargeInterval(50, 80)
    assert "[Standard]" in (
        battery / "charge_types"
    ).read_text(encoding="utf-8")
