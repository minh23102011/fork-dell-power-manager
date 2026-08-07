import json

import pytest

from powerdeck_backends.telemetry import PowerTelemetrySample
from powerdeck_daemon.api import SystemApi


class FakeAuthorizer:
    async def authorize(
        self,
        sender: str,
        action_id: str,
        *,
        details: dict[str, str] | None = None,
        allow_interaction: bool = True,
    ) -> bool:
        return True


class FakeTelemetry:
    def sample(self) -> PowerTelemetrySample:
        return PowerTelemetrySample(
            cpu_watts=7.25,
            gpu_watts=1.5,
            fan_rpm=3210,
            cpu_source="rapl",
            gpu_source="energy-gpu",
            fan_source="fan1_input",
        )


@pytest.mark.asyncio
async def test_telemetry_is_readable_without_polkit_write() -> None:
    api = SystemApi(
        telemetry_reader=FakeTelemetry(),
        authorizer=FakeAuthorizer(),
    )

    payload = json.loads(await api.get_telemetry_state())

    assert payload["cpu_watts"] == 7.25
    assert payload["gpu_watts"] == 1.5
    assert payload["fan_rpm"] == 3210
