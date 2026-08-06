import io
import json

from powerdeck_backends.thermal.controller import (
    ThermalControlStatus,
    ThermalProfileApplyResult,
)
from powerdeck_core.models import ThermalProfile
from powerdeck_daemon.thermalctl import run


class FakeController:
    def read_status(self) -> ThermalControlStatus:
        return ThermalControlStatus(
            current_profile=ThermalProfile.QUIET,
            available_profiles=(
                ThermalProfile.COOL,
                ThermalProfile.QUIET,
                ThermalProfile.BALANCED,
                ThermalProfile.PERFORMANCE,
            ),
            source="test",
            profile_path="/fake/profile",
        )

    def apply(
        self,
        value: str | ThermalProfile,
    ) -> ThermalProfileApplyResult:
        requested = (
            value
            if isinstance(value, ThermalProfile)
            else ThermalProfile(value)
        )
        return ThermalProfileApplyResult(
            requested_profile=requested,
            previous_profile=ThermalProfile.QUIET,
            current_profile=requested,
            changed=requested is not ThermalProfile.QUIET,
            verified=True,
            source="test",
            profile_path="/fake/profile",
        )


def test_get_json() -> None:
    stdout = io.StringIO()

    result = run(
        ["get", "--json"],
        controller=FakeController(),
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert result == 0
    assert payload["current_profile"] == "quiet"
    assert payload["available_profiles"] == [
        "cool",
        "quiet",
        "balanced",
        "performance",
    ]


def test_set_json() -> None:
    stdout = io.StringIO()

    result = run(
        ["set", "balanced", "--json"],
        controller=FakeController(),
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert result == 0
    assert payload["previous_profile"] == "quiet"
    assert payload["current_profile"] == "balanced"
    assert payload["verified"] is True
