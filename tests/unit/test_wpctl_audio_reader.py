import subprocess
from collections.abc import Sequence

from powerdeck_backends.desktop.audio import WpctlAudioReader


class FakeRunner:
    def __init__(
        self,
        responses: dict[
            str,
            tuple[int, str, str],
        ],
    ) -> None:
        self.responses = responses
        self.calls: list[tuple[tuple[str, ...], float]] = []

    def __call__(
        self,
        args: Sequence[str],
        *,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        normalized = tuple(args)
        self.calls.append((normalized, timeout))
        returncode, stdout, stderr = self.responses[normalized[-1]]
        return subprocess.CompletedProcess(
            normalized,
            returncode,
            stdout=stdout,
            stderr=stderr,
        )


def test_reads_default_sink_and_source() -> None:
    runner = FakeRunner(
        {
            "@DEFAULT_AUDIO_SINK@": (0, "Volume: 0.80\n", ""),
            "@DEFAULT_AUDIO_SOURCE@": (
                0,
                "Volume: 0.25 [MUTED]\n",
                "",
            ),
        }
    )

    state = WpctlAudioReader(runner=runner).read()

    assert state.available is True
    assert state.backend == "wpctl"
    assert state.sink_volume == 0.8
    assert state.sink_muted is False
    assert state.source_volume == 0.25
    assert state.source_muted is True
    assert runner.calls == [
        (
            (
                "wpctl",
                "get-volume",
                "@DEFAULT_AUDIO_SINK@",
            ),
            2.0,
        ),
        (
            (
                "wpctl",
                "get-volume",
                "@DEFAULT_AUDIO_SOURCE@",
            ),
            2.0,
        ),
    ]


def test_accepts_amplified_volume_and_case_insensitive_mute() -> None:
    runner = FakeRunner(
        {
            "@DEFAULT_AUDIO_SINK@": (
                0,
                "Volume: 1.25 [muted]\n",
                "",
            ),
            "@DEFAULT_AUDIO_SOURCE@": (3, "", "not found"),
        }
    )

    state = WpctlAudioReader(runner=runner).read()

    assert state.available is True
    assert state.sink_volume == 1.25
    assert state.sink_muted is True
    assert state.source_volume is None
    assert state.source_muted is None


def test_one_missing_endpoint_keeps_audio_available() -> None:
    runner = FakeRunner(
        {
            "@DEFAULT_AUDIO_SINK@": (0, "Volume: 0.50\n", ""),
            "@DEFAULT_AUDIO_SOURCE@": (3, "", "not found"),
        }
    )

    state = WpctlAudioReader(runner=runner).read()

    assert state.available is True
    assert state.sink_volume == 0.5
    assert state.source_volume is None


def test_malformed_output_returns_unavailable() -> None:
    runner = FakeRunner(
        {
            "@DEFAULT_AUDIO_SINK@": (0, "unexpected\n", ""),
            "@DEFAULT_AUDIO_SOURCE@": (0, "Volume: nope\n", ""),
        }
    )

    state = WpctlAudioReader(runner=runner).read()

    assert state.available is False
    assert state.backend is None
    assert state.sink_volume is None
    assert state.source_volume is None


def test_missing_wpctl_returns_unavailable() -> None:
    def missing_runner(
        args: Sequence[str],
        *,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        del args, timeout
        raise FileNotFoundError("wpctl")

    state = WpctlAudioReader(runner=missing_runner).read()

    assert state.available is False
    assert state.backend is None
