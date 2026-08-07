from pathlib import Path


def test_system_service_exposes_telemetry_method() -> None:
    source = Path(
        "src/powerdeck_daemon/system_service.py"
    ).read_text(encoding="utf-8")

    assert 'method name="GetTelemetryState"' in source
    assert "get_telemetry_state()" in source


def test_client_has_telemetry_method() -> None:
    source = Path(
        "src/powerdeck_daemon/client.py"
    ).read_text(encoding="utf-8")

    assert "def get_telemetry_state" in source
    assert '"GetTelemetryState"' in source
