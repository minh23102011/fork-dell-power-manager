"""Read-only AC adapter discovery through the Linux power-supply class."""

from __future__ import annotations

from pathlib import Path

from powerdeck_core.models import AcAdapterState

_DEFAULT_POWER_SUPPLY_ROOT = Path("/sys/class/power_supply")
_ADAPTER_TYPES = frozenset({"Mains", "USB", "USB_C", "Wireless"})


def _read_text(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    return value or None


def _read_online(path: Path) -> bool | None:
    value = _read_text(path)
    if value == "0":
        return False
    if value == "1":
        return True
    return None


class SysfsAcAdapterReader:
    """Read AC adapter state without mutating the power-supply class."""

    def __init__(self, root: Path = _DEFAULT_POWER_SUPPLY_ROOT) -> None:
        self.root = root

    def read(self) -> tuple[AcAdapterState, ...]:
        try:
            candidates = sorted(
                (path for path in self.root.iterdir() if path.is_dir()),
                key=lambda path: path.name,
            )
        except OSError:
            return ()

        adapters: list[AcAdapterState] = []
        for path in candidates:
            adapter_type = _read_text(path / "type")
            if adapter_type not in _ADAPTER_TYPES:
                continue
            adapters.append(
                AcAdapterState(
                    name=path.name,
                    online=_read_online(path / "online"),
                    adapter_type=adapter_type,
                    manufacturer=_read_text(path / "manufacturer"),
                    model_name=_read_text(path / "model_name"),
                )
            )
        return tuple(adapters)


__all__ = ["SysfsAcAdapterReader"]
