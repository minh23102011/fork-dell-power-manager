"""Transactional privileged control for Intel P-state battery limits."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from powerdeck_core.errors import (
    CommandExecutionError,
    MissingCapabilityError,
    PermissionDeniedError,
    RollbackError,
    StateVerificationError,
)
from powerdeck_core.models import SerializableModel
from powerdeck_core.validation import validate_cpu_performance_percent

_DEFAULT_ROOT = Path("/sys/devices/system/cpu/intel_pstate")
type ReadText = Callable[[Path], str | None]
type WriteText = Callable[[Path, str], None]


@dataclass(frozen=True, slots=True)
class CpuPolicyStatus(SerializableModel):
    disable_turbo: bool | None
    max_performance_percent: int | None
    source: str | None


@dataclass(frozen=True, slots=True)
class CpuPolicyApplyResult(SerializableModel):
    previous_disable_turbo: bool
    previous_max_performance_percent: int
    current_disable_turbo: bool
    current_max_performance_percent: int
    changed: bool
    verified: bool
    source: str


def _read_text(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    return value or None


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


class IntelPstateController:
    def __init__(
        self,
        root: Path = _DEFAULT_ROOT,
        *,
        read_text: ReadText | None = None,
        write_text: WriteText | None = None,
    ) -> None:
        self.root = root
        self._read_text = read_text or _read_text
        self._write_text = write_text or _write_text

    @property
    def no_turbo_path(self) -> Path:
        return self.root / "no_turbo"

    @property
    def max_perf_path(self) -> Path:
        return self.root / "max_perf_pct"

    def read_status(self) -> CpuPolicyStatus:
        no_turbo = self._read_text(self.no_turbo_path)
        max_perf = self._read_text(self.max_perf_path)
        try:
            disable_turbo = None if no_turbo is None else bool(int(no_turbo))
            maximum = None if max_perf is None else int(max_perf)
        except ValueError:
            disable_turbo = None
            maximum = None
        source = (
            "intel_pstate"
            if disable_turbo is not None and maximum is not None
            else None
        )
        return CpuPolicyStatus(
            disable_turbo=disable_turbo,
            max_performance_percent=maximum,
            source=source,
        )

    def _write(self, path: Path, value: int) -> None:
        try:
            self._write_text(path, f"{value}\n")
        except PermissionError as error:
            raise PermissionDeniedError(
                "Permission denied while changing Intel P-state policy.",
                component="cpu",
                details={"path": str(path), "value": value},
            ) from error
        except OSError as error:
            raise CommandExecutionError(
                "The kernel rejected an Intel P-state write.",
                component="cpu",
                details={
                    "path": str(path),
                    "value": value,
                    "reason": str(error),
                },
            ) from error

    def apply(
        self,
        disable_turbo: bool,
        max_performance_percent: object,
    ) -> CpuPolicyApplyResult:
        before = self.read_status()
        if (
            before.disable_turbo is None
            or before.max_performance_percent is None
        ):
            raise MissingCapabilityError(
                "Intel P-state controls are unavailable.",
                component="cpu",
            )
        maximum = validate_cpu_performance_percent(
            max_performance_percent
        )
        if (
            before.disable_turbo == disable_turbo
            and before.max_performance_percent == maximum
        ):
            return CpuPolicyApplyResult(
                previous_disable_turbo=before.disable_turbo,
                previous_max_performance_percent=(
                    before.max_performance_percent
                ),
                current_disable_turbo=disable_turbo,
                current_max_performance_percent=maximum,
                changed=False,
                verified=True,
                source="intel_pstate",
            )

        self._write(self.no_turbo_path, int(disable_turbo))
        self._write(self.max_perf_path, maximum)
        after = self.read_status()
        if (
            after.disable_turbo == disable_turbo
            and after.max_performance_percent == maximum
        ):
            return CpuPolicyApplyResult(
                previous_disable_turbo=before.disable_turbo,
                previous_max_performance_percent=(
                    before.max_performance_percent
                ),
                current_disable_turbo=disable_turbo,
                current_max_performance_percent=maximum,
                changed=True,
                verified=True,
                source="intel_pstate",
            )

        self._write(self.max_perf_path, before.max_performance_percent)
        self._write(self.no_turbo_path, int(before.disable_turbo))
        restored = self.read_status()
        if restored != before:
            raise RollbackError(
                "CPU policy verification failed and rollback failed.",
                component="cpu",
            )
        raise StateVerificationError(
            "CPU policy verification failed; previous values were restored.",
            component="cpu",
        )


__all__ = [
    "CpuPolicyApplyResult",
    "CpuPolicyStatus",
    "IntelPstateController",
]
