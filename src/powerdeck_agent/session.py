"""Battery Saver apply/restore orchestration for the user session."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from powerdeck_agent.settings import SaverSettings, load_settings
from powerdeck_backends.scanner import PowerDeckScanner
from powerdeck_core.capabilities import (
    find_battery_refresh_mode,
    select_internal_output,
)
from powerdeck_core.transactions import should_restore_setting
from powerdeck_daemon.client import SystemClient

STATE_PATH = Path("~/.local/state/powerdeck/saver-state.json").expanduser()


@dataclass(frozen=True, slots=True)
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


def _run(
    args: tuple[str, ...],
    *,
    timeout: float = 8.0,
) -> CommandResult:
    environment = dict(os.environ)
    if "NIRI_SOCKET" not in environment:
        runtime = Path(f"/run/user/{os.getuid()}")
        sockets = sorted(runtime.glob("niri.*.sock"))
        if sockets:
            environment["NIRI_SOCKET"] = str(sockets[-1])

    result = subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=environment,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"{' '.join(args)} failed: {detail or result.returncode}"
        )
    return CommandResult(
        stdout=result.stdout.strip(),
        stderr=result.stderr.strip(),
        returncode=result.returncode,
    )


def _read_int(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
        text=True,
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                payload,
                stream,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _read_state() -> dict[str, Any]:
    try:
        value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"active": False, "changes": {}}
    return (
        value
        if isinstance(value, dict)
        else {"active": False, "changes": {}}
    )


def _record_change(
    state: dict[str, Any],
    key: str,
    before: Any,
    applied: Any,
) -> None:
    changes = state.setdefault("changes", {})
    if not isinstance(changes, dict):
        changes = {}
        state["changes"] = changes
    changes[key] = {"before": before, "applied": applied}
    state["active"] = True
    _atomic_json(STATE_PATH, state)


def _on_ac_power() -> bool | None:
    root = Path("/sys/class/power_supply")
    try:
        directories = tuple(path for path in root.iterdir() if path.is_dir())
    except OSError:
        return None
    values: list[bool] = []
    for directory in directories:
        try:
            supply_type = (
                directory / "type"
            ).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if supply_type not in {"Mains", "USB", "USB_C"}:
            continue
        online = _read_int(directory / "online")
        if online is not None:
            values.append(bool(online))
    return any(values) if values else None


class SessionController:
    def __init__(self) -> None:
        self.scanner = PowerDeckScanner()

    @staticmethod
    async def _with_client(method: str, *args: object) -> dict[str, Any]:
        client = await SystemClient.connect()
        try:
            operation = getattr(client, method)
            result = await operation(*args)
            return result
        finally:
            client.disconnect()

    @staticmethod
    def _backlight_paths() -> tuple[Path, Path, str] | None:
        root = Path("/sys/class/backlight")
        try:
            devices = sorted(
                (path for path in root.iterdir() if path.is_dir()),
                key=lambda path: path.name,
            )
        except OSError:
            return None
        if not devices:
            return None
        device = devices[0]
        return (
            device / "brightness",
            device / "max_brightness",
            device.name,
        )

    def _apply_brightness(
        self,
        settings: SaverSettings,
        state: dict[str, Any],
    ) -> None:
        paths = self._backlight_paths()
        if paths is None:
            return
        current_path, maximum_path, device = paths
        current = _read_int(current_path)
        maximum = _read_int(maximum_path)
        if current is None or maximum in {None, 0}:
            return
        target = round(maximum * settings.brightness_cap_percent / 100)
        target = max(1, min(target, maximum))
        if settings.only_lower_brightness and current <= target:
            return
        _run(("brightnessctl", "-d", device, "set", str(target)))
        observed = _read_int(current_path)
        if observed is None:
            raise RuntimeError("brightness verification failed")
        _record_change(state, "brightness", current, observed)

    def _display_values(
        self,
        target_hz: float,
    ) -> tuple[str, str, str] | None:
        snapshot = self.scanner.scan()
        output = select_internal_output(snapshot.status.displays)
        if output is None or output.current_mode is None:
            return None
        target = find_battery_refresh_mode(
            output,
            target_hz=target_hz,
        )
        if target is None:
            return None
        before = output.current_mode.label
        applied = target.label
        return output.connector, before, applied

    def _apply_display(
        self,
        settings: SaverSettings,
        state: dict[str, Any],
    ) -> None:
        values = self._display_values(
            settings.target_refresh_rate_hz
        )
        if values is None:
            return
        connector, before, applied = values
        if before == applied:
            return
        _run(("niri", "msg", "output", connector, "mode", applied))
        _record_change(
            state,
            "display",
            {"connector": connector, "mode": before},
            {"connector": connector, "mode": applied},
        )

    def _power_profile(self) -> str | None:
        try:
            return _run(("powerprofilesctl", "get")).stdout or None
        except (OSError, RuntimeError, subprocess.SubprocessError):
            return None

    def _apply_power_profile(
        self,
        settings: SaverSettings,
        state: dict[str, Any],
    ) -> None:
        before = self._power_profile()
        if before is None or before == settings.power_profile:
            return
        _run(("powerprofilesctl", "set", settings.power_profile))
        after = self._power_profile()
        if after != settings.power_profile:
            raise RuntimeError("power profile verification failed")
        _record_change(
            state,
            "power_profile",
            before,
            settings.power_profile,
        )

    def _apply_thermal(
        self,
        settings: SaverSettings,
        state: dict[str, Any],
    ) -> None:
        before = asyncio.run(
            self._with_client("get_thermal_state")
        ).get("current_profile")
        result = asyncio.run(
            self._with_client(
                "set_thermal_profile",
                settings.thermal_profile,
            )
        )
        after = result.get("current_profile")
        if after != settings.thermal_profile:
            raise RuntimeError("thermal profile verification failed")
        if before != after:
            _record_change(state, "thermal_profile", before, after)

    def _apply_cpu(
        self,
        settings: SaverSettings,
        state: dict[str, Any],
    ) -> None:
        before_payload = asyncio.run(
            self._with_client("get_cpu_state")
        )
        result = asyncio.run(
            self._with_client(
                "set_cpu_policy",
                settings.disable_turbo,
                settings.max_performance_percent,
            )
        )
        before = {
            "disable_turbo": before_payload.get("disable_turbo"),
            "max_performance_percent": before_payload.get(
                "max_performance_percent"
            ),
        }
        applied = {
            "disable_turbo": result.get("current_disable_turbo"),
            "max_performance_percent": result.get(
                "current_max_performance_percent"
            ),
        }
        if before != applied:
            _record_change(state, "cpu_policy", before, applied)

    @staticmethod
    def _keyboard_device() -> tuple[str, Path] | None:
        root = Path("/sys/class/leds")
        try:
            devices = sorted(
                (
                    path
                    for path in root.iterdir()
                    if path.is_dir() and "kbd" in path.name.lower()
                ),
                key=lambda path: path.name,
            )
        except OSError:
            return None
        if not devices:
            return None
        return devices[0].name, devices[0] / "brightness"

    def _apply_keyboard(
        self,
        settings: SaverSettings,
        state: dict[str, Any],
    ) -> None:
        device = self._keyboard_device()
        if device is None:
            return
        name, path = device
        before = _read_int(path)
        if before is None or before == settings.keyboard_backlight_level:
            return
        _run(
            (
                "brightnessctl",
                "-d",
                name,
                "set",
                str(settings.keyboard_backlight_level),
            )
        )
        after = _read_int(path)
        if after is None:
            raise RuntimeError("keyboard backlight verification failed")
        _record_change(state, "keyboard_backlight", before, after)

    @staticmethod
    def _sink_muted() -> bool | None:
        try:
            output = _run(
                ("wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@")
            ).stdout.lower()
        except (OSError, RuntimeError, subprocess.SubprocessError):
            return None
        return "muted" in output

    def _apply_audio(
        self,
        settings: SaverSettings,
        state: dict[str, Any],
    ) -> None:
        if not settings.mute_audio:
            return
        before = self._sink_muted()
        if before is None or before:
            return
        _run(
            (
                "wpctl",
                "set-mute",
                "@DEFAULT_AUDIO_SINK@",
                "1",
            )
        )
        after = self._sink_muted()
        if after is not True:
            raise RuntimeError("audio mute verification failed")
        _record_change(state, "audio_muted", before, after)

    def apply_now(
        self,
        settings: SaverSettings | None = None,
    ) -> dict[str, Any]:
        active_settings = settings or load_settings()
        state: dict[str, Any] = {
            "active": False,
            "started_at": time.time(),
            "changes": {},
        }
        _atomic_json(STATE_PATH, state)
        operations = (
            lambda: self._apply_brightness(active_settings, state),
            lambda: self._apply_display(active_settings, state),
            lambda: self._apply_power_profile(active_settings, state),
            lambda: self._apply_thermal(active_settings, state),
            lambda: self._apply_cpu(active_settings, state),
            lambda: self._apply_keyboard(active_settings, state),
            lambda: self._apply_audio(active_settings, state),
        )
        try:
            for operation in operations:
                operation()
        except Exception:
            self.restore_now()
            raise
        state["active"] = bool(state.get("changes"))
        state["completed_at"] = time.time()
        _atomic_json(STATE_PATH, state)
        return state

    def _current_for_key(self, key: str) -> Any:
        if key == "brightness":
            paths = self._backlight_paths()
            return None if paths is None else _read_int(paths[0])
        if key == "power_profile":
            return self._power_profile()
        if key == "thermal_profile":
            return asyncio.run(
                self._with_client("get_thermal_state")
            ).get("current_profile")
        if key == "cpu_policy":
            payload = asyncio.run(
                self._with_client("get_cpu_state")
            )
            return {
                "disable_turbo": payload.get("disable_turbo"),
                "max_performance_percent": payload.get(
                    "max_performance_percent"
                ),
            }
        if key == "keyboard_backlight":
            device = self._keyboard_device()
            return None if device is None else _read_int(device[1])
        if key == "audio_muted":
            return self._sink_muted()
        if key == "display":
            snapshot = self.scanner.scan()
            output = select_internal_output(snapshot.status.displays)
            if output is None or output.current_mode is None:
                return None
            return {
                "connector": output.connector,
                "mode": output.current_mode.label,
            }
        return None

    def _restore_key(self, key: str, value: Any) -> None:
        if key == "brightness":
            paths = self._backlight_paths()
            if paths is not None:
                _run(
                    (
                        "brightnessctl",
                        "-d",
                        paths[2],
                        "set",
                        str(int(value)),
                    )
                )
        elif key == "display" and isinstance(value, dict):
            _run(
                (
                    "niri",
                    "msg",
                    "output",
                    str(value["connector"]),
                    "mode",
                    str(value["mode"]),
                )
            )
        elif key == "power_profile":
            _run(("powerprofilesctl", "set", str(value)))
        elif key == "thermal_profile":
            asyncio.run(
                self._with_client(
                    "set_thermal_profile",
                    str(value),
                )
            )
        elif key == "cpu_policy" and isinstance(value, dict):
            asyncio.run(
                self._with_client(
                    "set_cpu_policy",
                    bool(value["disable_turbo"]),
                    int(value["max_performance_percent"]),
                )
            )
        elif key == "keyboard_backlight":
            device = self._keyboard_device()
            if device is not None:
                _run(
                    (
                        "brightnessctl",
                        "-d",
                        device[0],
                        "set",
                        str(int(value)),
                    )
                )
        elif key == "audio_muted":
            _run(
                (
                    "wpctl",
                    "set-mute",
                    "@DEFAULT_AUDIO_SINK@",
                    "1" if bool(value) else "0",
                )
            )

    def restore_now(self) -> dict[str, Any]:
        state = _read_state()
        changes = state.get("changes", {})
        if not isinstance(changes, dict):
            changes = {}
        restored: list[str] = []
        skipped: list[str] = []
        for key, change in reversed(tuple(changes.items())):
            if not isinstance(change, dict):
                continue
            before = change.get("before")
            applied = change.get("applied")
            current = self._current_for_key(key)
            if should_restore_setting(current, applied):
                self._restore_key(key, before)
                restored.append(key)
            else:
                skipped.append(key)
        result = {
            "active": False,
            "restored": restored,
            "skipped": skipped,
            "completed_at": time.time(),
        }
        _atomic_json(STATE_PATH, result)
        return result

    def status(self) -> dict[str, Any]:
        state = _read_state()
        state["on_ac_power"] = _on_ac_power()
        state["settings"] = asdict(load_settings())
        return state


def run_forever() -> None:
    controller = SessionController()
    while True:
        settings = load_settings()
        state = _read_state()
        active = bool(state.get("active"))
        on_ac = _on_ac_power()
        try:
            if (
                settings.enabled
                and settings.auto_enable_on_battery
                and on_ac is False
                and not active
            ):
                controller.apply_now(settings)
            elif (
                settings.restore_on_ac
                and on_ac is True
                and active
            ):
                controller.restore_now()
        except Exception as error:
            state["last_error"] = f"{type(error).__name__}: {error}"
            state["last_error_at"] = time.time()
            _atomic_json(STATE_PATH, state)
        time.sleep(3.0)


__all__ = [
    "STATE_PATH",
    "SessionController",
    "run_forever",
]
