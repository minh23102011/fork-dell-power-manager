import pytest

from powerdeck_core.errors import ValidationError
from powerdeck_core.models import ChargeMode, ThermalProfile
from powerdeck_core.validation import (
    validate_brightness_cap,
    validate_charge_interval,
    validate_charge_mode,
    validate_cpu_performance_percent,
    validate_refresh_rate,
    validate_thermal_profile,
)


@pytest.mark.parametrize(
    ("start", "end"),
    [(50, 55), (60, 65), (95, 100), (50, 80)],
)
def test_valid_charge_intervals(start: int, end: int) -> None:
    result = validate_charge_interval(start, end)
    assert result.start_percent == start
    assert result.end_percent == end


@pytest.mark.parametrize(
    ("start", "end"),
    [(49, 80), (50, 54), (90, 90), (96, 100), (50, 101)],
)
def test_invalid_charge_intervals(start: int, end: int) -> None:
    with pytest.raises(ValidationError):
        validate_charge_interval(start, end)


def test_bool_is_not_accepted_as_integer() -> None:
    with pytest.raises(ValidationError):
        validate_brightness_cap(True)


def test_profile_validation_against_capability_set() -> None:
    assert validate_charge_mode("primarily-ac") is ChargeMode.PRIMARILY_AC
    assert validate_thermal_profile("quiet", [ThermalProfile.QUIET]) is ThermalProfile.QUIET
    with pytest.raises(ValidationError):
        validate_thermal_profile("performance", [ThermalProfile.QUIET])


def test_numeric_ranges() -> None:
    assert validate_brightness_cap(40) == 40
    assert validate_cpu_performance_percent(60) == 60
    assert validate_refresh_rate(60.012) == 60.012
    with pytest.raises(ValidationError):
        validate_refresh_rate(float("nan"))
