import subprocess
from collections.abc import Sequence

from powerdeck_backends.system.power_manager import PowerManagerReader
from powerdeck_core.models import ServiceActivity


class FakeRunner:
    def __init__(self, responses: dict[tuple[str, ...], tuple[int, str, str]]) -> None:
        self.responses = responses

    def __call__(
        self,
        args: Sequence[str],
        *,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        del timeout
        key = tuple(args)
        returncode, stdout, stderr = self.responses.get(key, (1, "", "missing"))
        return subprocess.CompletedProcess(key, returncode, stdout, stderr)


def _systemctl_key(unit: str) -> tuple[str, ...]:
    return (
        "systemctl",
        "show",
        "--property=LoadState",
        "--property=ActiveState",
        unit,
    )


def test_detects_power_profiles_daemon_and_profiles() -> None:
    responses = {
        _systemctl_key("power-profiles-daemon.service"): (
            0,
            "LoadState=loaded\nActiveState=active\n",
            "",
        ),
        _systemctl_key("tuned.service"): (
            0,
            "LoadState=loaded\nActiveState=inactive\n",
            "",
        ),
        ("powerprofilesctl", "get"): (0, "balanced\n", ""),
        ("powerprofilesctl", "list"): (
            0,
            "  performance:\n* balanced:\n  power-saver:\n",
            "",
        ),
    }

    state = PowerManagerReader(FakeRunner(responses)).read()

    assert state.provider == "power-profiles-daemon"
    assert state.current_profile == "balanced"
    assert state.available_profiles == (
        "performance",
        "balanced",
        "power-saver",
    )
    assert state.services[0].activity is ServiceActivity.ACTIVE
    assert state.services[1].activity is ServiceActivity.INACTIVE


def test_multiple_active_managers_have_no_single_provider() -> None:
    responses = {
        _systemctl_key("power-profiles-daemon.service"): (
            0,
            "LoadState=loaded\nActiveState=active\n",
            "",
        ),
        _systemctl_key("tlp.service"): (
            0,
            "LoadState=loaded\nActiveState=active\n",
            "",
        ),
    }

    state = PowerManagerReader(FakeRunner(responses)).read()

    assert state.provider is None
    assert state.has_conflict is True


def test_not_found_service_is_reported() -> None:
    responses = {
        _systemctl_key("power-profiles-daemon.service"): (
            0,
            "LoadState=not-found\nActiveState=inactive\n",
            "",
        )
    }

    state = PowerManagerReader(FakeRunner(responses)).read()

    service = state.services[0]
    assert service.installed is False
    assert service.activity is ServiceActivity.NOT_INSTALLED
