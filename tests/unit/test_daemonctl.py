import io
import json
from typing import Any

from powerdeck_daemon.daemonctl import run


class FakeClient:
    def __init__(self) -> None:
        self.disconnected = False
        self.requested_profile: str | None = None

    async def ping(self) -> str:
        return "pong"

    async def get_thermal_state(self) -> dict[str, Any]:
        return {
            "current_profile": "quiet",
            "available_profiles": [
                "cool",
                "quiet",
                "balanced",
                "performance",
            ],
        }

    async def set_thermal_profile(
        self,
        profile: str,
    ) -> dict[str, Any]:
        self.requested_profile = profile
        return {
            "previous_profile": "quiet",
            "current_profile": profile,
            "verified": True,
        }

    def disconnect(self) -> None:
        self.disconnected = True


def test_ping() -> None:
    client = FakeClient()
    stdout = io.StringIO()

    result = run(
        ["ping"],
        client=client,
        stdout=stdout,
    )

    assert result == 0
    assert stdout.getvalue() == "pong\n"
    assert client.disconnected is True


def test_get_thermal_json() -> None:
    client = FakeClient()
    stdout = io.StringIO()

    result = run(
        ["thermal", "get", "--json"],
        client=client,
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert result == 0
    assert payload["current_profile"] == "quiet"


def test_set_thermal_json() -> None:
    client = FakeClient()
    stdout = io.StringIO()

    result = run(
        ["thermal", "set", "balanced", "--json"],
        client=client,
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert result == 0
    assert client.requested_profile == "balanced"
    assert payload["current_profile"] == "balanced"
