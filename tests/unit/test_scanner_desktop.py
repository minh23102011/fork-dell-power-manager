
from powerdeck_backends.scanner import PowerDeckScanner
from powerdeck_core.models import (
    AcAdapterState,
    BatteryInfo,
    BrightnessDevice,
    ChargeCapabilities,
    ChargeState,
    CpuCapabilities,
    DisplayMode,
    DisplayOutput,
    KeyboardBacklightDevice,
    MachineInfo,
    PowerManagerState,
    ThermalCapabilities,
    ThermalState,
)


class FakeBattery:
    def read_batteries(self) -> tuple[BatteryInfo, ...]:
        return ()

    def read_charge_capabilities(self) -> ChargeCapabilities:
        return ChargeCapabilities()

    def read_charge_state(self) -> ChargeState:
        return ChargeState()


class FakeThermal:
    def read_capabilities(self) -> ThermalCapabilities:
        return ThermalCapabilities()

    def read_state(self) -> ThermalState:
        return ThermalState()


class FakeCpu:
    def read_capabilities(self) -> CpuCapabilities:
        return CpuCapabilities()


class FakeMachine:
    def read(self) -> MachineInfo:
        return MachineInfo(product_name="Test laptop")


class FakeAcAdapters:
    def read(self) -> tuple[AcAdapterState, ...]:
        return ()


class FakePowerManager:
    def read(self) -> PowerManagerState:
        return PowerManagerState()


class FakeDisplays:
    def __init__(self) -> None:
        self.output = DisplayOutput(
            connector="eDP-1",
            internal=True,
            modes=(
                DisplayMode(
                    width=1920,
                    height=1080,
                    refresh_hz=120.0,
                    current=True,
                ),
            ),
        )

    def read(self) -> tuple[DisplayOutput, ...]:
        return (self.output,)


class FakeBrightness:
    def __init__(self) -> None:
        self.device = BrightnessDevice(
            name="intel_backlight",
            device_class="raw",
            current=50,
            maximum=100,
            current_percent=50.0,
        )

    def read_brightness_devices(self) -> tuple[BrightnessDevice, ...]:
        return (self.device,)


class FakeKeyboard:
    def __init__(self) -> None:
        self.device = KeyboardBacklightDevice(
            name="dell::kbd_backlight",
            current_level=1,
            maximum_level=2,
            available_levels=(0, 1, 2),
        )

    def read_keyboard_backlights(
        self,
    ) -> tuple[KeyboardBacklightDevice, ...]:
        return (self.device,)


def test_scanner_integrates_desktop_readers() -> None:
    displays = FakeDisplays()
    brightness = FakeBrightness()
    keyboard = FakeKeyboard()

    scanner = PowerDeckScanner(
        battery=FakeBattery(),
        thermal=FakeThermal(),
        cpu=FakeCpu(),
        machine=FakeMachine(),
        ac_adapters=FakeAcAdapters(),
        power_manager=FakePowerManager(),
        displays=displays,
        brightness=brightness,
        keyboard_backlights=keyboard,
    )

    snapshot = scanner.scan()

    assert scanner.displays is displays
    assert scanner.brightness is brightness
    assert scanner.keyboard_backlights is keyboard

    assert snapshot.capabilities.displays == (displays.output,)
    assert snapshot.capabilities.brightness_devices == (brightness.device,)
    assert snapshot.capabilities.keyboard_backlights == (keyboard.device,)

    assert snapshot.status.displays == (displays.output,)
    assert snapshot.status.brightness_devices == (brightness.device,)
    assert snapshot.status.keyboard_backlights == (keyboard.device,)
