"""Pure validation helpers used by UI, CLI and privileged services."""

from __future__ import annotations

import math
from collections.abc import Iterable

from powerdeck_core.errors import ValidationError
from powerdeck_core.models import ChargeInterval, ChargeMode, ThermalProfile


def require_int(name: str, value: object) -> int:
    """Return an integer while rejecting booleans and lossy coercion."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{name} must be an integer", component="validation")
    return value


def require_percent(name: str, value: object, *, minimum: int = 0, maximum: int = 100) -> int:
    integer = require_int(name, value)
    if integer < minimum or integer > maximum:
        raise ValidationError(
            f"{name} must be between {minimum} and {maximum}",
            component="validation",
            details={"name": name, "value": integer, "minimum": minimum, "maximum": maximum},
        )
    return integer


def validate_charge_interval(
    start_percent: object,
    end_percent: object,
    *,
    start_min: int = 50,
    start_max: int = 95,
    end_min: int = 55,
    end_max: int = 100,
    minimum_gap: int = 5,
) -> ChargeInterval:
    start = require_percent(
        "charge start threshold",
        start_percent,
        minimum=start_min,
        maximum=start_max,
    )
    end = require_percent(
        "charge end threshold",
        end_percent,
        minimum=end_min,
        maximum=end_max,
    )
    if end - start < minimum_gap:
        raise ValidationError(
            f"charge end threshold must be at least {minimum_gap}% above start threshold",
            component="battery",
            details={"start": start, "end": end, "minimum_gap": minimum_gap},
        )
    return ChargeInterval(start_percent=start, end_percent=end)


def validate_brightness_cap(value: object) -> int:
    return require_percent("brightness cap", value, minimum=1, maximum=100)


def validate_cpu_performance_percent(value: object) -> int:
    return require_percent("maximum CPU performance", value, minimum=1, maximum=100)


def validate_refresh_rate(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValidationError("refresh rate must be numeric", component="display")
    refresh = float(value)
    if not math.isfinite(refresh) or refresh <= 0.0 or refresh > 1000.0:
        raise ValidationError(
            "refresh rate must be finite and between 0 and 1000 Hz",
            component="display",
            details={"value": refresh},
        )
    return refresh


def validate_charge_mode(
    value: str | ChargeMode,
    available: Iterable[ChargeMode] | None = None,
) -> ChargeMode:
    try:
        mode = value if isinstance(value, ChargeMode) else ChargeMode(value.replace("-", "_"))
    except ValueError as error:
        raise ValidationError(
            f"unsupported charging mode: {value}",
            component="battery",
        ) from error
    if available is not None and mode not in set(available):
        raise ValidationError(
            f"charging mode is not available on this machine: {mode.value}",
            component="battery",
        )
    return mode


def validate_thermal_profile(
    value: str | ThermalProfile,
    available: Iterable[ThermalProfile] | None = None,
) -> ThermalProfile:
    try:
        profile = value if isinstance(value, ThermalProfile) else ThermalProfile(value)
    except ValueError as error:
        raise ValidationError(
            f"unsupported thermal profile: {value}",
            component="thermal",
        ) from error
    if available is not None and profile not in set(available):
        raise ValidationError(
            f"thermal profile is not available on this machine: {profile.value}",
            component="thermal",
        )
    return profile


__all__ = [
    "require_int",
    "require_percent",
    "validate_brightness_cap",
    "validate_charge_interval",
    "validate_charge_mode",
    "validate_cpu_performance_percent",
    "validate_refresh_rate",
    "validate_thermal_profile",
]
