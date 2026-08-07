from powerdeck_backends.battery.charge_types import (
    mode_from_charge_type,
    parse_charge_types,
)
from powerdeck_core.models import ChargeMode


def test_parses_bracketed_active_mode() -> None:
    parsed = parse_charge_types(
        "Trickle Fast Standard Adaptive [Custom]"
    )

    assert parsed.choices == (
        "Trickle",
        "Fast",
        "Standard",
        "Adaptive",
        "Custom",
    )
    assert parsed.active_raw == "Custom"
    assert parsed.active_mode is ChargeMode.CUSTOM


def test_maps_fast_to_express_without_mapping_trickle() -> None:
    assert mode_from_charge_type("Fast") is ChargeMode.EXPRESS
    assert mode_from_charge_type("Trickle") is None


def test_single_plain_value_is_treated_as_active() -> None:
    parsed = parse_charge_types("Standard")

    assert parsed.choices == ("Standard",)
    assert parsed.active_raw == "Standard"


def test_available_modes_are_deduplicated() -> None:
    parsed = parse_charge_types(
        "Fast Express Standard [Custom]"
    )

    assert parsed.available_modes == (
        ChargeMode.EXPRESS,
        ChargeMode.STANDARD,
        ChargeMode.CUSTOM,
    )


def test_resolves_original_raw_token_for_write() -> None:
    parsed = parse_charge_types(
        "Adaptive Standard Fast [Custom]"
    )

    assert parsed.raw_for_mode(ChargeMode.EXPRESS) == "Fast"
