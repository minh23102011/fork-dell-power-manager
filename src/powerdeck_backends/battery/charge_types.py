"""Shared parsing and mapping for Linux battery charge-type sysfs files."""

from __future__ import annotations

import re
from dataclasses import dataclass

from powerdeck_core.models import ChargeMode

_ACTIVE_PATTERN = re.compile(r"\[([^\]]+)\]")
_SEPARATOR_PATTERN = re.compile(r"[\[\],]")

_MODE_ALIASES: dict[str, ChargeMode] = {
    "adaptive": ChargeMode.ADAPTIVE,
    "standard": ChargeMode.STANDARD,
    "normal": ChargeMode.STANDARD,
    "fast": ChargeMode.EXPRESS,
    "express": ChargeMode.EXPRESS,
    "express_charge": ChargeMode.EXPRESS,
    "expresscharge": ChargeMode.EXPRESS,
    "primarily_ac": ChargeMode.PRIMARILY_AC,
    "primarilyac": ChargeMode.PRIMARILY_AC,
    "ac": ChargeMode.PRIMARILY_AC,
    "custom": ChargeMode.CUSTOM,
}


@dataclass(frozen=True, slots=True)
class ParsedChargeTypes:
    """Choices and active raw token from a kernel charge-types string."""

    choices: tuple[str, ...]
    active_raw: str | None

    @property
    def active_mode(self) -> ChargeMode | None:
        return mode_from_charge_type(self.active_raw)

    @property
    def available_modes(self) -> tuple[ChargeMode, ...]:
        modes: list[ChargeMode] = []
        for choice in self.choices:
            mode = mode_from_charge_type(choice)
            if mode is not None and mode not in modes:
                modes.append(mode)
        if self.active_mode is not None and self.active_mode not in modes:
            modes.append(self.active_mode)
        return tuple(modes)

    def raw_for_mode(self, mode: ChargeMode) -> str | None:
        return next(
            (
                choice
                for choice in self.choices
                if mode_from_charge_type(choice) is mode
            ),
            None,
        )


def normalize_charge_type(value: str) -> str:
    """Normalize a kernel token without conflating unknown modes."""

    return re.sub(
        r"[^a-z0-9]+",
        "_",
        value.strip().lower(),
    ).strip("_")


def mode_from_charge_type(value: str | None) -> ChargeMode | None:
    if value is None:
        return None
    return _MODE_ALIASES.get(normalize_charge_type(value))


def parse_charge_types(text: str | None) -> ParsedChargeTypes:
    """Parse both bracketed lists and single-value compatibility files."""

    if text is None:
        return ParsedChargeTypes(choices=(), active_raw=None)

    match = _ACTIVE_PATTERN.search(text)
    active = match.group(1).strip() if match is not None else None

    cleaned = _SEPARATOR_PATTERN.sub(" ", text)
    choices = tuple(
        dict.fromkeys(
            token
            for token in cleaned.split()
            if token
        )
    )

    # A regular test fixture or a legacy kernel may expose one plain value.
    if active is None and len(choices) == 1:
        active = choices[0]

    return ParsedChargeTypes(
        choices=choices,
        active_raw=active,
    )


__all__ = [
    "ParsedChargeTypes",
    "mode_from_charge_type",
    "normalize_charge_type",
    "parse_charge_types",
]
