"""Transport-independent privileged system API."""

from __future__ import annotations

import asyncio
from typing import Protocol

from powerdeck_backends.thermal.controller import (
    PlatformProfileController,
    ThermalControlStatus,
    ThermalProfileApplyResult,
)
from powerdeck_core.errors import PermissionDeniedError
from powerdeck_core.models import ThermalProfile
from powerdeck_daemon.constants import ACTION_SET_THERMAL_PROFILE


class Authorizer(Protocol):
    async def authorize(
        self,
        sender: str,
        action_id: str,
        *,
        details: dict[str, str] | None = None,
        allow_interaction: bool = True,
    ) -> bool: ...


class ThermalController(Protocol):
    def read_status(self) -> ThermalControlStatus: ...

    def apply(
        self,
        value: str | ThermalProfile,
    ) -> ThermalProfileApplyResult: ...


class SystemApi:
    """Privileged operations exposed through the system D-Bus service."""

    def __init__(
        self,
        *,
        controller: ThermalController | None = None,
        authorizer: Authorizer,
    ) -> None:
        self.controller: ThermalController = (
            controller
            if controller is not None
            else PlatformProfileController()
        )
        self.authorizer = authorizer

    async def get_thermal_state(self) -> str:
        status = await asyncio.to_thread(self.controller.read_status)
        return status.to_json(indent=None)

    async def set_thermal_profile(
        self,
        sender: str,
        profile: str,
    ) -> str:
        if not sender:
            raise PermissionDeniedError(
                "The D-Bus caller identity is unavailable.",
                component="authorization",
            )

        authorized = await self.authorizer.authorize(
            sender,
            ACTION_SET_THERMAL_PROFILE,
            details={"profile": profile},
            allow_interaction=True,
        )
        if not authorized:
            raise PermissionDeniedError(
                "Authorization to change the thermal profile was denied.",
                component="thermal",
                details={"profile": profile},
            )

        result = await asyncio.to_thread(
            self.controller.apply,
            profile,
        )
        return result.to_json(indent=None)


__all__ = [
    "Authorizer",
    "SystemApi",
    "ThermalController",
]
