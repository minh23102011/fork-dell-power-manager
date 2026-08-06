"""Stable names shared by PowerDeck system-service components."""

BUS_NAME = "org.powerdeck.System1"
OBJECT_PATH = "/org/powerdeck/System1"
INTERFACE = "org.powerdeck.System1"

ACTION_MANAGE_POWER = "org.powerdeck.system.manage-power"
ACTION_SET_THERMAL_PROFILE = ACTION_MANAGE_POWER
ACTION_SET_CHARGE_CONTROL = ACTION_MANAGE_POWER
ACTION_SET_CPU_POLICY = ACTION_MANAGE_POWER

__all__ = [
    "ACTION_MANAGE_POWER",
    "ACTION_SET_CHARGE_CONTROL",
    "ACTION_SET_CPU_POLICY",
    "ACTION_SET_THERMAL_PROFILE",
    "BUS_NAME",
    "INTERFACE",
    "OBJECT_PATH",
]
