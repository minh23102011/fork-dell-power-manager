from powerdeck_backends.scanner import PowerDeckScanner
from powerdeck_core.models import (
    AcAdapterState,
    BatteryInfo,
    ChargeCapabilities,
    ChargeMode,
    ChargeState,
    CpuCapabilities,
    MachineInfo,
    PowerManagerState,
    ThermalCapabilities,
    ThermalProfile,
    ThermalState,
)


class FakeBatteryReader:
    def read_batteries(self) -> tuple[BatteryInfo, ...]:
        return (BatteryInfo(name="BAT0", capacity_percent=79),)

    def read_charge_capabilities(self) -> ChargeCapabilities:
        return ChargeCapabilities(
            available=True,
            provider="test",
            supported_modes=(ChargeMode.CUSTOM,),
            custom_thresholds=True,
        )

    def read_charge_state(self) -> ChargeState:
        return ChargeState(battery_name="BAT0", mode=ChargeMode.CUSTOM)


class FakeThermalReader:
    def read_capabilities(self) -> ThermalCapabilities:
        return ThermalCapabilities(
            available=True,
            provider="test",
            supported_profiles=(ThermalProfile.BALANCED,),
        )

    def read_state(self) -> ThermalState:
        return ThermalState(current_profile=ThermalProfile.BALANCED)


class FakeCpuReader:
    def read_capabilities(self) -> CpuCapabilities:
        return CpuCapabilities(
            model_name="Test CPU",
            scaling_driver="intel_pstate",
        )


class FakeMachineReader:
    def read(self) -> MachineInfo:
        return MachineInfo(vendor="Dell Inc.", product_name="Test Laptop")


class FakeAcReader:
    def read(self) -> tuple[AcAdapterState, ...]:
        return (AcAdapterState(name="AC", online=True),)


class FakePowerManagerReader:
    def read(self) -> PowerManagerState:
        return PowerManagerState(provider="power-profiles-daemon")


def test_scanner_aggregates_current_backends() -> None:
    snapshot = PowerDeckScanner(
        battery=FakeBatteryReader(),
        thermal=FakeThermalReader(),
        cpu=FakeCpuReader(),
        machine=FakeMachineReader(),
        ac_adapters=FakeAcReader(),
        power_manager=FakePowerManagerReader(),
    ).scan()

    assert snapshot.status.machine.product_name == "Test Laptop"
    assert snapshot.status.batteries[0].capacity_percent == 79
    assert snapshot.status.on_ac_power is True
    assert snapshot.capabilities.charge.available is True
    assert snapshot.capabilities.thermal.available is True
    assert snapshot.capabilities.cpu.scaling_driver == "intel_pstate"
    assert snapshot.capabilities.ac_monitoring is True
    assert snapshot.status.power_manager.provider == "power-profiles-daemon"
    assert any(
        issue.code == "internal-display-not-found"
        for issue in snapshot.status.diagnostics
    )


def test_snapshot_serializes_capabilities_and_status() -> None:
    snapshot = PowerDeckScanner(
        battery=FakeBatteryReader(),
        thermal=FakeThermalReader(),
        cpu=FakeCpuReader(),
        machine=FakeMachineReader(),
        ac_adapters=FakeAcReader(),
        power_manager=FakePowerManagerReader(),
    ).scan()

    payload = snapshot.to_dict()

    assert payload["schema_version"] == 1
    assert payload["capabilities"]["charge"]["available"] is True
    assert payload["status"]["batteries"][0]["name"] == "BAT0"
