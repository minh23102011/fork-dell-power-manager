from pathlib import Path


def test_app_reads_telemetry_from_system_daemon() -> None:
    source = Path(
        "src/powerdeck_app/main.py"
    ).read_text(encoding="utf-8")

    assert "get_telemetry_state" in source
    assert "PowerTelemetrySampler" not in source
    assert "powerdeck-telemetry" in source
    assert "await asyncio.sleep(1.5)" in source
