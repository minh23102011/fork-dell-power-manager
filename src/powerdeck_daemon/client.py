"""Async client for the PowerDeck system D-Bus service."""

from __future__ import annotations

import json
from typing import Any

from dbus_next.aio import MessageBus
from dbus_next.constants import BusType
from dbus_next.errors import DBusError
from dbus_next.message import Message

from powerdeck_core.errors import ServiceUnavailableError
from powerdeck_daemon.constants import BUS_NAME, INTERFACE, OBJECT_PATH


class SystemClient:
    def __init__(self, bus: MessageBus) -> None:
        self.bus = bus

    @classmethod
    async def connect(cls) -> SystemClient:
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        return cls(bus)

    def disconnect(self) -> None:
        self.bus.disconnect()

    async def _call(
        self,
        member: str,
        *,
        signature: str = "",
        body: list[object] | None = None,
    ) -> str:
        message = Message(
            destination=BUS_NAME,
            path=OBJECT_PATH,
            interface=INTERFACE,
            member=member,
            signature=signature,
            body=body or [],
        )
        try:
            reply = await self.bus.call(message)
        except DBusError as error:
            raise ServiceUnavailableError(
                "The PowerDeck system service rejected the request.",
                component="daemon-client",
                details={"member": member, "reason": str(error)},
            ) from error

        if reply is None or not reply.body:
            raise ServiceUnavailableError(
                "The PowerDeck system service returned no result.",
                component="daemon-client",
                details={"member": member},
            )
        value = reply.body[0]
        if not isinstance(value, str):
            raise ServiceUnavailableError(
                "The PowerDeck system service returned malformed data.",
                component="daemon-client",
                details={"member": member},
            )
        return value

    async def ping(self) -> str:
        return await self._call("Ping")

    async def get_thermal_state(self) -> dict[str, Any]:
        return _decode_json(await self._call("GetThermalState"))

    async def set_thermal_profile(
        self,
        profile: str,
    ) -> dict[str, Any]:
        return _decode_json(
            await self._call(
                "SetThermalProfile",
                signature="s",
                body=[profile],
            )
        )

    async def get_charge_state(self) -> dict[str, Any]:
        return _decode_json(await self._call("GetChargeState"))

    async def set_charge_mode(
        self,
        mode: str,
    ) -> dict[str, Any]:
        return _decode_json(
            await self._call(
                "SetChargeMode",
                signature="s",
                body=[mode],
            )
        )

    async def set_charge_thresholds(
        self,
        start_percent: int,
        end_percent: int,
    ) -> dict[str, Any]:
        return _decode_json(
            await self._call(
                "SetChargeThresholds",
                signature="ii",
                body=[start_percent, end_percent],
            )
        )

    async def get_cpu_state(self) -> dict[str, Any]:
        return _decode_json(await self._call("GetCpuState"))

    async def set_cpu_policy(
        self,
        disable_turbo: bool,
        max_performance_percent: int,
    ) -> dict[str, Any]:
        return _decode_json(
            await self._call(
                "SetCpuPolicy",
                signature="bi",
                body=[disable_turbo, max_performance_percent],
            )
        )


def _decode_json(payload: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ServiceUnavailableError(
            "The PowerDeck system service returned invalid JSON.",
            component="daemon-client",
        ) from error
    if not isinstance(value, dict):
        raise ServiceUnavailableError(
            "The PowerDeck system service returned a non-object result.",
            component="daemon-client",
        )
    return value


__all__ = ["SystemClient"]
