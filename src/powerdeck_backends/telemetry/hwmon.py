"""Read fan RPM values from the Linux hwmon class."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from powerdeck_core.models import SerializableModel


@dataclass(frozen=True, slots=True)
class FanReading(SerializableModel):
    label: str
    rpm: int | None
    source_path: str


class HwmonFanReader:
    """Discover read-only fan tachometer values.

    PowerDeck intentionally does not write pwm* controls here. Laptop firmware
    remains responsible for direct RPM regulation.
    """

    def __init__(
        self,
        root: Path = Path("/sys/class/hwmon"),
    ) -> None:
        self.root = root

    @staticmethod
    def _read_text(path: Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            return None

    @staticmethod
    def _parse_int(value: str | None) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def read(self) -> tuple[FanReading, ...]:
        if not self.root.is_dir():
            return ()

        readings: list[FanReading] = []
        for hwmon in sorted(self.root.glob("hwmon*")):
            device_name = self._read_text(hwmon / "name") or hwmon.name
            for input_path in sorted(hwmon.glob("fan[0-9]*_input")):
                stem = input_path.name.removesuffix("_input")
                label = self._read_text(hwmon / f"{stem}_label")
                rpm = self._parse_int(self._read_text(input_path))
                readings.append(
                    FanReading(
                        label=label or f"{device_name} {stem}",
                        rpm=rpm,
                        source_path=str(input_path),
                    )
                )
        return tuple(readings)


__all__ = ["FanReading", "HwmonFanReader"]
