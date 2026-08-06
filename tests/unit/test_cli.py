import io

from powerdeck_backends.scanner import DiscoverySnapshot
from powerdeck_cli.main import run
from powerdeck_core.models import (
    BatteryInfo,
    ChargeCapabilities,
    ChargeMode,
    ChargeState,
    CpuCapabilities,
    MachineInfo,
    PowerDeckCapabilities,
    PowerDeckStatus,
    ThermalCapabilities,
    ThermalProfile,
    ThermalState,
)


class FakeScanner:
    def scan(self) -> DiscoverySnapshot:
        capabilities = PowerDeckCapabilities(
            charge=ChargeCapabilities(available=True),
            thermal=ThermalCapabilities(available=True),
            cpu=CpuCapabilities(
                model_name="Test CPU",
                scaling_driver="intel_pstate",
                current_governor="powersave",
            ),
            ac_monitoring=True,
        )
        status = PowerDeckStatus(
            machine=MachineInfo(
                vendor="Dell Inc.",
                product_name="Test Laptop",
                os_name="CachyOS Linux",
                kernel_release="test-kernel",
            ),
            batteries=(
                BatteryInfo(
                    name="BAT0",
                    capacity_percent=79,
                    status="Discharging",
                ),
            ),
            charge=ChargeState(mode=ChargeMode.CUSTOM),
            thermal=ThermalState(current_profile=ThermalProfile.BALANCED),
        )
        return DiscoverySnapshot(1, capabilities, status)


def test_status_human_output() -> None:
    stdout = io.StringIO()

    result = run(["status"], scanner=FakeScanner(), stdout=stdout)

    assert result == 0
    assert "Dell Inc. Test Laptop" in stdout.getvalue()
    assert "Battery BAT0: 79%" in stdout.getvalue()
    assert "Thermal profile: balanced" in stdout.getvalue()


def test_status_json_output() -> None:
    stdout = io.StringIO()

    result = run(
        ["status", "--json", "--compact"],
        scanner=FakeScanner(),
        stdout=stdout,
    )

    assert result == 0
    assert '"capabilities"' in stdout.getvalue()
    assert '"Test Laptop"' in stdout.getvalue()


def test_compact_requires_json() -> None:
    stderr = io.StringIO()

    result = run(["status", "--compact"], scanner=FakeScanner(), stderr=stderr)

    assert result == 2
    assert "requires --json" in stderr.getvalue()
