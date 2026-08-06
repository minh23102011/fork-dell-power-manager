import json

import pytest

from powerdeck_backends.thermal.controller import (
    ThermalControlStatus,
    ThermalProfileApplyResult,
)
from powerdeck_core.errors import PermissionDeniedError
from powerdeck_core.models import ThermalProfile
from powerdeck_daemon.api import SystemApi
from powerdeck_daemon.constants import ACTION_SET_THERMAL_PROFILE


class FakeAuthorizer:
    def __init__(self, authorized: bool) -> None:
        self.authorized = authorized
        self.calls: list[tuple[str, str, dict[str, str] | None, bool]] = []

    async def authorize(
        self,
        sender: str,
        action_id: str,
        *,
        details: dict[str, str] | None = None,
        allow_interaction: bool = True,
    ) -> bool:
        self.calls.append(
            (
                sender,
                action_id,
                details,
                allow_interaction,
            )
        )
        return self.authorized


class FakeController:
    def __init__(self) -> None:
        self.applied: list[str | ThermalProfile] = []

    def read_status(self) -> ThermalControlStatus:
        return ThermalControlStatus(
            current_profile=ThermalProfile.QUIET,
            available_profiles=(
                ThermalProfile.QUIET,
                ThermalProfile.BALANCED,
            ),
            source="test",
            profile_path="/fake/profile",
        )

    def apply(
        self,
        value: str | ThermalProfile,
    ) -> ThermalProfileApplyResult:
        self.applied.append(value)
        profile = (
            value
            if isinstance(value, ThermalProfile)
            else ThermalProfile(value)
        )
        return ThermalProfileApplyResult(
            requested_profile=profile,
            previous_profile=ThermalProfile.QUIET,
            current_profile=profile,
            changed=profile is not ThermalProfile.QUIET,
            verified=True,
            source="test",
            profile_path="/fake/profile",
        )


@pytest.mark.asyncio
async def test_get_thermal_state_is_json() -> None:
    api = SystemApi(
        controller=FakeController(),
        authorizer=FakeAuthorizer(True),
    )

    payload = json.loads(await api.get_thermal_state())

    assert payload["current_profile"] == "quiet"
    assert payload["available_profiles"] == [
        "quiet",
        "balanced",
    ]


@pytest.mark.asyncio
async def test_authorized_profile_change_is_applied() -> None:
    authorizer = FakeAuthorizer(True)
    controller = FakeController()
    api = SystemApi(
        controller=controller,
        authorizer=authorizer,
    )

    payload = json.loads(
        await api.set_thermal_profile(":1.42", "balanced")
    )

    assert payload["current_profile"] == "balanced"
    assert controller.applied == ["balanced"]
    assert authorizer.calls == [
        (
            ":1.42",
            ACTION_SET_THERMAL_PROFILE,
            {"profile": "balanced"},
            True,
        )
    ]


@pytest.mark.asyncio
async def test_denied_profile_change_does_not_write() -> None:
    controller = FakeController()
    api = SystemApi(
        controller=controller,
        authorizer=FakeAuthorizer(False),
    )

    with pytest.raises(PermissionDeniedError):
        await api.set_thermal_profile(":1.42", "balanced")

    assert controller.applied == []


@pytest.mark.asyncio
async def test_missing_sender_is_denied() -> None:
    controller = FakeController()
    api = SystemApi(
        controller=controller,
        authorizer=FakeAuthorizer(True),
    )

    with pytest.raises(PermissionDeniedError):
        await api.set_thermal_profile("", "balanced")

    assert controller.applied == []
