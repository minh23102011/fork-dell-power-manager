from pathlib import Path

from powerdeck_backends.system.intel_pstate_control import (
    IntelPstateController,
)


def test_applies_cpu_policy(tmp_path: Path) -> None:
    (tmp_path / "no_turbo").write_text("0\n", encoding="utf-8")
    (tmp_path / "max_perf_pct").write_text("100\n", encoding="utf-8")
    controller = IntelPstateController(tmp_path)

    result = controller.apply(True, 60)

    assert result.verified is True
    assert result.current_disable_turbo is True
    assert result.current_max_performance_percent == 60


def test_same_policy_is_idempotent(tmp_path: Path) -> None:
    (tmp_path / "no_turbo").write_text("1\n", encoding="utf-8")
    (tmp_path / "max_perf_pct").write_text("60\n", encoding="utf-8")
    controller = IntelPstateController(tmp_path)

    result = controller.apply(True, 60)

    assert result.changed is False
