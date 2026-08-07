"""Pure-Python UI specification for the PowerDeck shell."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NavigationItem:
    key: str
    title: str
    icon_name: str


NAVIGATION: tuple[NavigationItem, ...] = (
    NavigationItem(
        key="battery",
        title="Battery",
        icon_name="battery-symbolic",
    ),
    NavigationItem(
        key="thermal",
        title="Thermal",
        icon_name="preferences-system-symbolic",
    ),
    NavigationItem(
        key="saver",
        title="Battery Saver",
        icon_name="power-profile-power-saver-symbolic",
    ),
)


__all__ = [
    "NAVIGATION",
    "NavigationItem",
]
