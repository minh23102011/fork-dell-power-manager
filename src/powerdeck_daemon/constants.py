"""Stable names shared by the PowerDeck system service and its clients."""

BUS_NAME = "org.powerdeck.System1"
OBJECT_PATH = "/org/powerdeck/System1"
INTERFACE = "org.powerdeck.System1"
ACTION_SET_THERMAL_PROFILE = "org.powerdeck.system.set-thermal-profile"

__all__ = [
    "ACTION_SET_THERMAL_PROFILE",
    "BUS_NAME",
    "INTERFACE",
    "OBJECT_PATH",
]
