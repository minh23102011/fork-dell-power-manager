from powerdeck_backends.scanner import PowerDeckScanner
from powerdeck_core.models import (
    AcAdapterState,
    AudioState,
    BatteryInfo,
    BrightnessDevice,
    ChargeCapabilities,
    ChargeMode,
    ChargeState,
    CpuCapabilities,
    DisplayOutput,
    KeyboardBacklightDevice,
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
        return ChargeState(
            battery_name="BAT0",
            mode=ChargeMode.CUSTOM,
        )


class FakeThermalReader:
    def read_capabilities(self) -> ThermalCapabilities:
        return ThermalCapabilities(
            available=True,
            provider="test",
            supported_profiles=(ThermalProfile.BALANCED,),
        )

    def read_state(self) -> ThermalState:
        return ThermalState(
            current_profile=ThermalProfile.BALANCED,
        )


class FakeCpuReader:
    def read_capabilities(self) -> CpuCapabilities:
        return CpuCapabilities(
            model_name="Test CPU",
            scaling_driver="intel_pstate",
        )


class FakeMachineReader:
    def read(self) -> MachineInfo:
        return MachineInfo(
            vendor="Dell Inc.",
            product_name="Test Laptop",
        )


class FakeAcReader:
    def read(self) -> tuple[AcAdapterState, ...]:
        return (AcAdapterState(name="AC", online=True),)


class FakePowerManagerReader:
    def read(self) -> PowerManagerState:
        return PowerManagerState(
            provider="power-profiles-daemon",
        )


class EmptyDisplayReader:
    def read(self) -> tuple[DisplayOutput, ...]:
        return ()


class EmptyBrightnessReader:
    def read_brightness_devices(
        self,
    ) -> tuple[BrightnessDevice, ...]:
        return ()


class EmptyKeyboardBacklightReader:
    def read_keyboard_backlights(
        self,
    ) -> tuple[KeyboardBacklightDevice, ...]:
        return ()


class EmptyAudioReader:
    def read(self) -> AudioState:
        return AudioState()


def _scanner() -> PowerDeckScanner:
    return PowerDeckScanner(
        battery=FakeBatteryReader(),
        thermal=FakeThermalReader(),
        cpu=FakeCpuReader(),
        machine=FakeMachineReader(),
        ac_adapters=FakeAcReader(),
        power_manager=FakePowerManagerReader(),
        displays=EmptyDisplayReader(),
        brightness=EmptyBrightnessReader(),
        keyboard_backlights=EmptyKeyboardBacklightReader(),
        audio=EmptyAudioReader(),
    )


def test_scanner_aggregates_current_backends() -> None:
    snapshot = _scanner().scan()

    assert snapshot.status.machine.product_name == "Test Laptop"
    assert snapshot.status.batteries[0].capacity_percent == 79
    assert snapshot.status.on_ac_power is True
    assert snapshot.capabilities.charge.available is True
    assert snapshot.capabilities.thermal.available is True
    assert snapshot.capabilities.cpu.scaling_driver == "intel_pstate"
    assert snapshot.capabilities.ac_monitoring is True
    assert snapshot.status.power_manager.provider == (
        "power-profiles-daemon"
    )
    assert any(
        issue.code == "internal-display-not-found"
        for issue in snapshot.status.diagnostics
    )
    assert any(
        issue.code == "audio-control-unavailable"
        for issue in snapshot.status.diagnostics
    )


def test_snapshot_serializes_capabilities_and_status() -> None:
    payload = _scanner().scan().to_dict()

    assert payload["schema_version"] == 1
    assert payload["capabilities"]["charge"]["available"] is True
    assert payload["status"]["batteries"][0]["name"] == "BAT0"
