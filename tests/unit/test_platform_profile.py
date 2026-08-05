from pathlib import Path

from powerdeck_backends.thermal.platform_profile import PlatformProfileReader
from powerdeck_core.models import ThermalProfile


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{value}\n", encoding="utf-8")


def _make_class_interface(
    root: Path,
    *,
    choices: str = "cool quiet balanced performance",
    profile: str = "balanced",
    provider: str | None = "dell-pc",
    name: str = "platform-profile-0",
) -> Path:
    interface = root / name
    _write(interface / "choices", choices)
    _write(interface / "profile", profile)
    if provider is not None:
        _write(interface / "provider", provider)
    return interface


def _make_thermal_zone(
    root: Path,
    name: str,
    *,
    zone_type: str,
    temperature_millicelsius: object,
) -> None:
    zone = root / name
    _write(zone / "type", zone_type)
    _write(zone / "temp", temperature_millicelsius)


def test_reads_class_platform_profile_and_temperatures(tmp_path: Path) -> None:
    profile_root = tmp_path / "platform-profile"
    thermal_root = tmp_path / "thermal"
    _make_class_interface(profile_root)
    _make_thermal_zone(
        thermal_root,
        "thermal_zone0",
        zone_type="x86_pkg_temp",
        temperature_millicelsius=51_250,
    )

    reader = PlatformProfileReader(
        platform_profile_root=profile_root,
        acpi_root=tmp_path / "acpi",
        thermal_root=thermal_root,
    )

    capabilities = reader.read_capabilities()
    state = reader.read_state()

    assert capabilities.available is True
    assert capabilities.provider == "dell-pc"
    assert capabilities.supported_profiles == (
        ThermalProfile.COOL,
        ThermalProfile.QUIET,
        ThermalProfile.BALANCED,
        ThermalProfile.PERFORMANCE,
    )
    assert state.current_profile is ThermalProfile.BALANCED
    assert state.temperatures_celsius == {"x86_pkg_temp": 51.25}
    assert state.source == "kernel-platform-profile-class"


def test_falls_back_to_acpi_compatibility_interface(tmp_path: Path) -> None:
    acpi_root = tmp_path / "acpi"
    _write(acpi_root / "platform_profile_choices", "quiet balanced performance")
    _write(acpi_root / "platform_profile", "quiet")

    reader = PlatformProfileReader(
        platform_profile_root=tmp_path / "missing-class",
        acpi_root=acpi_root,
        thermal_root=tmp_path / "missing-thermal",
    )

    capabilities = reader.read_capabilities()
    state = reader.read_state()

    assert capabilities.available is True
    assert capabilities.provider == "kernel-platform-profile"
    assert capabilities.supported_profiles == (
        ThermalProfile.QUIET,
        ThermalProfile.BALANCED,
        ThermalProfile.PERFORMANCE,
    )
    assert state.current_profile is ThermalProfile.QUIET
    assert state.source == "kernel-platform-profile-acpi"


def test_class_interface_is_preferred_over_acpi_fallback(tmp_path: Path) -> None:
    profile_root = tmp_path / "platform-profile"
    acpi_root = tmp_path / "acpi"
    _make_class_interface(profile_root, profile="performance")
    _write(acpi_root / "platform_profile_choices", "quiet balanced")
    _write(acpi_root / "platform_profile", "quiet")

    state = PlatformProfileReader(
        platform_profile_root=profile_root,
        acpi_root=acpi_root,
        thermal_root=tmp_path / "thermal",
    ).read_state()

    assert state.current_profile is ThermalProfile.PERFORMANCE
    assert state.source == "kernel-platform-profile-class"


def test_unknown_profiles_are_ignored_and_current_profile_is_preserved(
    tmp_path: Path,
) -> None:
    profile_root = tmp_path / "platform-profile"
    _make_class_interface(
        profile_root,
        choices="quiet turbo balanced",
        profile="performance",
        provider=None,
    )

    capabilities = PlatformProfileReader(
        platform_profile_root=profile_root,
        acpi_root=tmp_path / "acpi",
        thermal_root=tmp_path / "thermal",
    ).read_capabilities()

    assert capabilities.provider == "kernel-platform-profile"
    assert capabilities.supported_profiles == (
        ThermalProfile.QUIET,
        ThermalProfile.BALANCED,
        ThermalProfile.PERFORMANCE,
    )


def test_duplicate_thermal_zone_names_remain_unique(tmp_path: Path) -> None:
    thermal_root = tmp_path / "thermal"
    _make_thermal_zone(
        thermal_root,
        "thermal_zone0",
        zone_type="acpitz",
        temperature_millicelsius=42_000,
    )
    _make_thermal_zone(
        thermal_root,
        "thermal_zone1",
        zone_type="acpitz",
        temperature_millicelsius=43_500,
    )

    temperatures = PlatformProfileReader(
        platform_profile_root=tmp_path / "profile",
        acpi_root=tmp_path / "acpi",
        thermal_root=thermal_root,
    ).read_temperatures()

    assert temperatures == {
        "acpitz": 42.0,
        "acpitz (thermal_zone1)": 43.5,
    }


def test_malformed_and_implausible_temperatures_are_ignored(
    tmp_path: Path,
) -> None:
    thermal_root = tmp_path / "thermal"
    _make_thermal_zone(
        thermal_root,
        "thermal_zone0",
        zone_type="bad-text",
        temperature_millicelsius="not-a-number",
    )
    _make_thermal_zone(
        thermal_root,
        "thermal_zone1",
        zone_type="too-hot",
        temperature_millicelsius=999_000,
    )
    _make_thermal_zone(
        thermal_root,
        "thermal_zone2",
        zone_type="valid",
        temperature_millicelsius=49_000,
    )

    state = PlatformProfileReader(
        platform_profile_root=tmp_path / "profile",
        acpi_root=tmp_path / "acpi",
        thermal_root=thermal_root,
    ).read_state()

    assert state.current_profile is None
    assert state.temperatures_celsius == {"valid": 49.0}
    assert state.source == "kernel-thermal-zone"


def test_missing_interfaces_return_unavailable_empty_state(tmp_path: Path) -> None:
    reader = PlatformProfileReader(
        platform_profile_root=tmp_path / "missing-profile",
        acpi_root=tmp_path / "missing-acpi",
        thermal_root=tmp_path / "missing-thermal",
    )

    capabilities = reader.read_capabilities()
    state = reader.read_state()

    assert capabilities.available is False
    assert capabilities.provider is None
    assert capabilities.supported_profiles == ()
    assert capabilities.writable is False
    assert state.current_profile is None
    assert state.temperatures_celsius is None
    assert state.source is None
