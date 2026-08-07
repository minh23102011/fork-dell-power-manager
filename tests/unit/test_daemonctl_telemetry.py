import io
import json
from typing import Any

from powerdeck_daemon.daemonctl import run


class FakeClient:
    def __init__(self) -> None:
        self.disconnected = False

    async def ping(self) -> str:
        return "pong"

    async def get_telemetry_state(self) -> dict[str, Any]:
        return {
            "cpu_watts": 5.5,
            "gpu_watts": 1.25,
            "fan_rpm": 4000,
        }

    async def get_thermal_state(self) -> dict[str, Any]:
        return {}

    async def set_thermal_profile(
        self,
        profile: str,
    ) -> dict[str, Any]:
        return {"current_profile": profile}

    def disconnect(self) -> None:
        self.disconnected = True


def test_telemetry_json() -> None:
    stdout = io.StringIO()
    client = FakeClient()

    result = run(
        ["telemetry", "--json"],
        client=client,
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert result == 0
    assert payload["cpu_watts"] == 5.5
    assert payload["gpu_watts"] == 1.25
    assert payload["fan_rpm"] == 4000
    assert client.disconnected is True
