"""Transport-independent privileged system API."""

from __future__ import annotations

import asyncio
from typing import Protocol

from powerdeck_backends.battery.controller import (
    ChargeApplyResult,
    ChargeControlStatus,
    SysfsChargeController,
)
from powerdeck_backends.system.intel_pstate_control import (
    CpuPolicyApplyResult,
    CpuPolicyStatus,
    IntelPstateController,
)
from powerdeck_backends.thermal.controller import (
    PlatformProfileController,
    ThermalControlStatus,
    ThermalProfileApplyResult,
)
from powerdeck_core.errors import PermissionDeniedError
from powerdeck_core.models import ChargeMode, ThermalProfile
from powerdeck_daemon.constants import ACTION_MANAGE_POWER


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


class ChargeController(Protocol):
    def read_status(self) -> ChargeControlStatus: ...

    def apply_mode(
        self,
        value: str | ChargeMode,
    ) -> ChargeApplyResult: ...

    def apply_custom(
        self,
        start_percent: object,
        end_percent: object,
    ) -> ChargeApplyResult: ...


class CpuController(Protocol):
    def read_status(self) -> CpuPolicyStatus: ...

    def apply(
        self,
        disable_turbo: bool,
        max_performance_percent: object,
    ) -> CpuPolicyApplyResult: ...


class SystemApi:
    def __init__(
        self,
        *,
        controller: ThermalController | None = None,
        thermal_controller: ThermalController | None = None,
        charge_controller: ChargeController | None = None,
        cpu_controller: CpuController | None = None,
        authorizer: Authorizer,
    ) -> None:
        selected_thermal = thermal_controller or controller
        self.thermal_controller: ThermalController = (
            selected_thermal
            if selected_thermal is not None
            else PlatformProfileController()
        )
        self.charge_controller: ChargeController = (
            charge_controller
            if charge_controller is not None
            else SysfsChargeController()
        )
        self.cpu_controller: CpuController = (
            cpu_controller
            if cpu_controller is not None
            else IntelPstateController()
        )
        self.authorizer = authorizer

    async def _authorize(
        self,
        sender: str,
        operation: str,
        details: dict[str, str],
    ) -> None:
        if not sender:
            raise PermissionDeniedError(
                "The D-Bus caller identity is unavailable.",
                component="authorization",
            )
        authorized = await self.authorizer.authorize(
            sender,
            ACTION_MANAGE_POWER,
            details={"operation": operation, **details},
            allow_interaction=True,
        )
        if not authorized:
            raise PermissionDeniedError(
                "Authorization to manage laptop power settings was denied.",
                component="authorization",
                details={"operation": operation, **details},
            )

    async def get_thermal_state(self) -> str:
        state = await asyncio.to_thread(
            self.thermal_controller.read_status
        )
        return state.to_json(indent=None)

    async def set_thermal_profile(
        self,
        sender: str,
        profile: str,
    ) -> str:
        await self._authorize(
            sender,
            "set-thermal-profile",
            {"profile": profile},
        )
        result = await asyncio.to_thread(
            self.thermal_controller.apply,
            profile,
        )
        return result.to_json(indent=None)

    async def get_charge_state(self) -> str:
        state = await asyncio.to_thread(
            self.charge_controller.read_status
        )
        return state.to_json(indent=None)

    async def set_charge_mode(
        self,
        sender: str,
        mode: str,
    ) -> str:
        await self._authorize(
            sender,
            "set-charge-mode",
            {"mode": mode},
        )
        result = await asyncio.to_thread(
            self.charge_controller.apply_mode,
            mode,
        )
        return result.to_json(indent=None)

    async def set_charge_thresholds(
        self,
        sender: str,
        start_percent: int,
        end_percent: int,
    ) -> str:
        await self._authorize(
            sender,
            "set-charge-thresholds",
            {
                "start_percent": str(start_percent),
                "end_percent": str(end_percent),
            },
        )
        result = await asyncio.to_thread(
            self.charge_controller.apply_custom,
            start_percent,
            end_percent,
        )
        return result.to_json(indent=None)

    async def get_cpu_state(self) -> str:
        state = await asyncio.to_thread(
            self.cpu_controller.read_status
        )
        return state.to_json(indent=None)

    async def set_cpu_policy(
        self,
        sender: str,
        disable_turbo: bool,
        max_performance_percent: int,
    ) -> str:
        await self._authorize(
            sender,
            "set-cpu-policy",
            {
                "disable_turbo": str(disable_turbo).lower(),
                "max_performance_percent": str(
                    max_performance_percent
                ),
            },
        )
        result = await asyncio.to_thread(
            self.cpu_controller.apply,
            disable_turbo,
            max_performance_percent,
        )
        return result.to_json(indent=None)


__all__ = [
    "Authorizer",
    "ChargeController",
    "CpuController",
    "SystemApi",
    "ThermalController",
]
