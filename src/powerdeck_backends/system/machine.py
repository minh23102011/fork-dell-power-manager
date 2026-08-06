"""Read-only machine and operating-system identification."""

from __future__ import annotations

import json
import platform
from collections.abc import Callable
from pathlib import Path

from powerdeck_core.models import MachineInfo

_DEFAULT_DMI_ROOT = Path("/sys/class/dmi/id")
_DEFAULT_OS_RELEASE_PATH = Path("/etc/os-release")


def _read_text(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    return value or None


def _parse_os_release(path: Path) -> dict[str, str]:
    text = _read_text(path)
    if text is None:
        return {}

    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, raw_value = stripped.partition("=")
        if not separator or not key:
            continue

        raw_value = raw_value.strip()
        if raw_value.startswith('"'):
            try:
                parsed = json.loads(raw_value)
            except json.JSONDecodeError:
                parsed = None
            value = parsed if isinstance(parsed, str) else raw_value.strip('"')
        else:
            value = raw_value.strip("'")
        values[key] = value
    return values


class MachineInfoReader:
    """Read stable machine metadata without requiring root privileges."""

    def __init__(
        self,
        dmi_root: Path = _DEFAULT_DMI_ROOT,
        os_release_path: Path = _DEFAULT_OS_RELEASE_PATH,
        kernel_release: Callable[[], str] = platform.release,
        architecture: Callable[[], str] = platform.machine,
    ) -> None:
        self.dmi_root = dmi_root
        self.os_release_path = os_release_path
        self.kernel_release = kernel_release
        self.architecture = architecture

    def read(self) -> MachineInfo:
        os_release = _parse_os_release(self.os_release_path)
        return MachineInfo(
            vendor=_read_text(self.dmi_root / "sys_vendor"),
            product_name=_read_text(self.dmi_root / "product_name"),
            product_family=_read_text(self.dmi_root / "product_family"),
            product_sku=_read_text(self.dmi_root / "product_sku"),
            product_version=_read_text(self.dmi_root / "product_version"),
            board_name=_read_text(self.dmi_root / "board_name"),
            board_version=_read_text(self.dmi_root / "board_version"),
            bios_vendor=_read_text(self.dmi_root / "bios_vendor"),
            bios_version=_read_text(self.dmi_root / "bios_version"),
            bios_date=_read_text(self.dmi_root / "bios_date"),
            os_name=os_release.get("PRETTY_NAME") or os_release.get("NAME"),
            os_id=os_release.get("ID"),
            kernel_release=self.kernel_release() or None,
            architecture=self.architecture() or None,
        )


__all__ = ["MachineInfoReader"]
