"""Read default PipeWire audio state through wpctl."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from typing import Protocol

from powerdeck_core.models import AudioState

_DEFAULT_SINK = "@DEFAULT_AUDIO_SINK@"
_DEFAULT_SOURCE = "@DEFAULT_AUDIO_SOURCE@"
_VOLUME_PATTERN = re.compile(
    r"Volume:\s*(?P<volume>(?:\d+(?:\.\d*)?|\.\d+))"
    r"(?:\s+\[(?P<muted>MUTED)\])?",
    re.IGNORECASE,
)


class CommandRunner(Protocol):
    def __call__(
        self,
        args: Sequence[str],
        *,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]: ...


def _run_command(
    args: Sequence[str],
    *,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _parse_volume(output: str) -> tuple[float, bool] | None:
    for line in output.splitlines():
        match = _VOLUME_PATTERN.search(line)
        if match is None:
            continue

        try:
            volume = float(match.group("volume"))
        except ValueError:
            return None

        if volume < 0:
            return None
        return volume, match.group("muted") is not None
    return None


class WpctlAudioReader:
    """Read default sink/source volume and mute state without changing them."""

    def __init__(
        self,
        runner: CommandRunner | None = None,
        timeout: float = 2.0,
    ) -> None:
        self.runner: CommandRunner = runner or _run_command
        self.timeout = timeout

    def _read_endpoint(
        self,
        target: str,
    ) -> tuple[float, bool] | None:
        try:
            result = self.runner(
                ("wpctl", "get-volume", target),
                timeout=self.timeout,
            )
        except (OSError, subprocess.SubprocessError):
            return None

        if result.returncode != 0:
            return None
        return _parse_volume(result.stdout)

    def read(self) -> AudioState:
        sink = self._read_endpoint(_DEFAULT_SINK)
        source = self._read_endpoint(_DEFAULT_SOURCE)
        available = sink is not None or source is not None

        return AudioState(
            available=available,
            sink_volume=sink[0] if sink is not None else None,
            sink_muted=sink[1] if sink is not None else None,
            source_volume=source[0] if source is not None else None,
            source_muted=source[1] if source is not None else None,
            backend="wpctl" if available else None,
        )


__all__ = ["CommandRunner", "WpctlAudioReader"]
