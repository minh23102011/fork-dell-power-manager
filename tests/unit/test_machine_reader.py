from pathlib import Path

from powerdeck_backends.system.machine import MachineInfoReader


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{value}\n", encoding="utf-8")


def test_reads_dmi_and_os_release(tmp_path: Path) -> None:
    dmi = tmp_path / "dmi"
    _write(dmi / "sys_vendor", "Dell Inc.")
    _write(dmi / "product_name", "Dell Inspiron 15 3530")
    _write(dmi / "bios_version", "1.30.0")
    os_release = tmp_path / "os-release"
    os_release.write_text(
        'NAME="CachyOS"\nPRETTY_NAME="CachyOS Linux"\nID=cachyos\n',
        encoding="utf-8",
    )

    machine = MachineInfoReader(
        dmi_root=dmi,
        os_release_path=os_release,
        kernel_release=lambda: "7.1.5-1-cachyos",
        architecture=lambda: "x86_64",
    ).read()

    assert machine.vendor == "Dell Inc."
    assert machine.product_name == "Dell Inspiron 15 3530"
    assert machine.bios_version == "1.30.0"
    assert machine.os_name == "CachyOS Linux"
    assert machine.os_id == "cachyos"
    assert machine.kernel_release == "7.1.5-1-cachyos"
    assert machine.architecture == "x86_64"


def test_missing_machine_files_return_partial_state(tmp_path: Path) -> None:
    machine = MachineInfoReader(
        dmi_root=tmp_path / "missing-dmi",
        os_release_path=tmp_path / "missing-os-release",
        kernel_release=lambda: "kernel",
        architecture=lambda: "arch",
    ).read()

    assert machine.vendor is None
    assert machine.os_name is None
    assert machine.kernel_release == "kernel"
    assert machine.architecture == "arch"
