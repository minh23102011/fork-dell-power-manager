"""Read Niri output state through its stable JSON IPC command."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from typing import Protocol

from powerdeck_core.models import DisplayMode, DisplayOutput


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


def _mapping(value: object) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    if not all(isinstance(key, str) for key in value):
        return None
    return value


def _sequence(value: object) -> Sequence[object] | None:
    if isinstance(value, Sequence) and not isinstance(
        value,
        str | bytes | bytearray,
    ):
        return value
    return None


def _string(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _boolean(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _refresh_hz(value: object) -> float | None:
    numeric = _number(value)
    if numeric is None or numeric <= 0:
        return None
    if numeric >= 1000:
        numeric /= 1000.0
    return round(numeric, 3)


def _unwrap_outputs(payload: object) -> object:
    root = _mapping(payload)
    if root is None:
        return payload

    ok = _mapping(root.get("Ok"))
    if ok is not None:
        return ok.get("Outputs", ok.get("outputs", ok))

    return root.get("Outputs", root.get("outputs", payload))


def _output_entries(
    payload: object,
) -> tuple[tuple[str, Mapping[str, object]], ...]:
    unwrapped = _unwrap_outputs(payload)
    mapping = _mapping(unwrapped)
    if mapping is not None:
        entries: list[tuple[str, Mapping[str, object]]] = []
        for connector, value in mapping.items():
            output = _mapping(value)
            if output is not None:
                entries.append((connector, output))
        return tuple(entries)

    sequence = _sequence(unwrapped)
    if sequence is None:
        return ()

    entries = []
    for value in sequence:
        output = _mapping(value)
        if output is None:
            continue
        connector_name = _string(output.get("name")) or _string(
            output.get("connector")
        )
        if connector_name is not None:
            entries.append((connector_name, output))
    return tuple(entries)


def _display_name(output: Mapping[str, object], connector: str) -> str | None:
    descriptive = tuple(
        value
        for key in ("make", "model", "serial")
        if (value := _string(output.get(key))) is not None
    )
    if descriptive:
        return " ".join(descriptive)

    name = _string(output.get("name"))
    if name is not None and name != connector:
        return name
    return None


def _mode_mapping(value: object) -> Mapping[str, object] | None:
    mode = _mapping(value)
    if mode is None:
        return None
    width = _integer(mode.get("width"))
    height = _integer(mode.get("height"))
    refresh = _refresh_hz(
        mode.get("refresh_rate", mode.get("refresh_millihz"))
    )
    if width is None or width <= 0:
        return None
    if height is None or height <= 0:
        return None
    if refresh is None:
        return None
    return mode


def _same_mode(
    left: Mapping[str, object],
    right: Mapping[str, object],
) -> bool:
    left_refresh = _refresh_hz(
        left.get("refresh_rate", left.get("refresh_millihz"))
    )
    right_refresh = _refresh_hz(
        right.get("refresh_rate", right.get("refresh_millihz"))
    )
    return (
        _integer(left.get("width")) == _integer(right.get("width"))
        and _integer(left.get("height")) == _integer(right.get("height"))
        and left_refresh is not None
        and right_refresh is not None
        and abs(left_refresh - right_refresh) < 0.001
    )


def _parse_modes(output: Mapping[str, object]) -> tuple[DisplayMode, ...]:
    raw_modes = _sequence(output.get("modes"))
    if raw_modes is None:
        return ()

    current_value = output.get("current_mode")
    current_index = _integer(current_value)
    current_mapping = _mapping(current_value)

    modes: list[DisplayMode] = []
    for index, value in enumerate(raw_modes):
        mode = _mode_mapping(value)
        if mode is None:
            continue

        refresh = _refresh_hz(
            mode.get("refresh_rate", mode.get("refresh_millihz"))
        )
        if refresh is None:
            continue

        preferred = _boolean(
            mode.get("is_preferred", mode.get("preferred"))
        )
        current = index == current_index
        if current_mapping is not None:
            current = _same_mode(mode, current_mapping)

        modes.append(
            DisplayMode(
                width=_integer(mode.get("width")) or 0,
                height=_integer(mode.get("height")) or 0,
                refresh_hz=refresh,
                current=current,
                preferred=preferred is True,
            )
        )
    return tuple(modes)


def _parse_output(
    connector: str,
    output: Mapping[str, object],
) -> DisplayOutput:
    logical = _mapping(output.get("logical"))
    current_mode = output.get("current_mode")
    enabled = logical is not None or current_mode is not None
    lower_connector = connector.lower()

    return DisplayOutput(
        connector=connector,
        name=_display_name(output, connector),
        internal=lower_connector.startswith(("edp", "lvds", "dsi")),
        enabled=enabled,
        variable_refresh_rate_supported=_boolean(
            output.get("vrr_supported")
        ),
        variable_refresh_rate_enabled=_boolean(output.get("vrr_enabled")),
        modes=_parse_modes(output),
    )


class NiriOutputReader:
    """Read outputs using ``niri msg --json outputs``."""

    def __init__(
        self,
        runner: CommandRunner | None = None,
        timeout: float = 2.0,
    ) -> None:
        self.runner: CommandRunner = runner or _run_command
        self.timeout = timeout

    def read(self) -> tuple[DisplayOutput, ...]:
        try:
            result = self.runner(
                ("niri", "msg", "--json", "outputs"),
                timeout=self.timeout,
            )
        except (OSError, subprocess.SubprocessError):
            return ()

        if result.returncode != 0:
            return ()

        try:
            payload: object = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError):
            return ()

        return tuple(
            _parse_output(connector, output)
            for connector, output in _output_entries(payload)
        )


__all__ = ["CommandRunner", "NiriOutputReader"]
