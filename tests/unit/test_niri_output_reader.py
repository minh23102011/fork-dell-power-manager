import json
import subprocess
from collections.abc import Sequence

from powerdeck_backends.desktop.niri import NiriOutputReader


class FakeRunner:
    def __init__(
        self,
        *,
        stdout: str,
        returncode: int = 0,
    ) -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.calls: list[tuple[tuple[str, ...], float]] = []

    def __call__(
        self,
        args: Sequence[str],
        *,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        normalized = tuple(args)
        self.calls.append((normalized, timeout))
        return subprocess.CompletedProcess(
            normalized,
            self.returncode,
            stdout=self.stdout,
            stderr="",
        )


def test_reads_niri_output_map() -> None:
    runner = FakeRunner(
        stdout=json.dumps(
            {
                "eDP-1": {
                    "make": "BOE",
                    "model": "NV156FHM",
                    "serial": None,
                    "modes": [
                        {
                            "width": 1920,
                            "height": 1080,
                            "refresh_rate": 120003,
                            "is_preferred": False,
                        },
                        {
                            "width": 1920,
                            "height": 1080,
                            "refresh_rate": 60012,
                            "is_preferred": True,
                        },
                    ],
                    "current_mode": 0,
                    "vrr_supported": False,
                    "vrr_enabled": False,
                    "logical": {
                        "x": 0,
                        "y": 0,
                        "width": 1920,
                        "height": 1080,
                        "scale": 1.0,
                    },
                }
            }
        )
    )

    outputs = NiriOutputReader(runner=runner).read()

    assert runner.calls == [
        (("niri", "msg", "--json", "outputs"), 2.0)
    ]
    assert len(outputs) == 1
    output = outputs[0]
    assert output.connector == "eDP-1"
    assert output.name == "BOE NV156FHM"
    assert output.internal is True
    assert output.enabled is True
    assert output.variable_refresh_rate_supported is False
    assert output.current_mode is not None
    assert output.current_mode.refresh_hz == 120.003
    assert output.modes[1].preferred is True


def test_accepts_wrapped_socket_response_and_mode_object() -> None:
    runner = FakeRunner(
        stdout=json.dumps(
            {
                "Ok": {
                    "Outputs": {
                        "HDMI-A-1": {
                            "name": "HDMI-A-1",
                            "modes": [
                                {
                                    "width": 2560,
                                    "height": 1440,
                                    "refresh_rate": 59950,
                                    "is_preferred": True,
                                }
                            ],
                            "current_mode": {
                                "width": 2560,
                                "height": 1440,
                                "refresh_rate": 59950,
                            },
                            "logical": {},
                        }
                    }
                }
            }
        )
    )

    output = NiriOutputReader(runner=runner).read()[0]

    assert output.connector == "HDMI-A-1"
    assert output.internal is False
    assert output.current_mode is not None
    assert output.current_mode.refresh_hz == 59.95


def test_unknown_fields_are_ignored() -> None:
    runner = FakeRunner(
        stdout=json.dumps(
            {
                "eDP-1": {
                    "future_field": {"anything": True},
                    "modes": [
                        {
                            "width": 1920,
                            "height": 1080,
                            "refresh_rate": 60000,
                            "future_mode_field": "ignored",
                        }
                    ],
                    "current_mode": 0,
                    "logical": {},
                }
            }
        )
    )

    outputs = NiriOutputReader(runner=runner).read()

    assert len(outputs) == 1
    assert outputs[0].current_mode is not None


def test_invalid_json_or_command_failure_returns_empty() -> None:
    invalid = NiriOutputReader(
        runner=FakeRunner(stdout="{not-json")
    ).read()
    failed = NiriOutputReader(
        runner=FakeRunner(stdout="{}", returncode=1)
    ).read()

    assert invalid == ()
    assert failed == ()


def test_missing_niri_returns_empty() -> None:
    def missing_runner(
        args: Sequence[str],
        *,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        del args, timeout
        raise FileNotFoundError("niri")

    assert NiriOutputReader(runner=missing_runner).read() == ()
