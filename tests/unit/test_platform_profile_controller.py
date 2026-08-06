from pathlib import Path

import pytest

from powerdeck_backends.thermal.controller import (
    PlatformProfileController,
)
from powerdeck_core.errors import (
    RollbackError,
    StateVerificationError,
    ValidationError,
)
from powerdeck_core.models import ThermalProfile


def _controller(
    tmp_path: Path,
    *,
    current: str = "quiet",
    choices: str = "cool quiet balanced performance",
    write_text=None,
) -> tuple[PlatformProfileController, Path]:
    root = tmp_path / "platform-profile"
    interface = root / "platform-profile-0"
    interface.mkdir(parents=True)
    (interface / "choices").write_text(
        f"{choices}\n",
        encoding="utf-8",
    )
    profile_path = interface / "profile"
    profile_path.write_text(f"{current}\n", encoding="utf-8")

    controller = PlatformProfileController(
        platform_profile_root=root,
        acpi_root=tmp_path / "acpi",
        write_text=write_text,
    )
    return controller, profile_path


def test_reads_control_status(tmp_path: Path) -> None:
    controller, profile_path = _controller(tmp_path)

    status = controller.read_status()

    assert status.current_profile is ThermalProfile.QUIET
    assert status.available_profiles == (
        ThermalProfile.COOL,
        ThermalProfile.QUIET,
        ThermalProfile.BALANCED,
        ThermalProfile.PERFORMANCE,
    )
    assert status.profile_path == str(profile_path)


def test_applies_and_verifies_profile(tmp_path: Path) -> None:
    controller, profile_path = _controller(tmp_path)

    result = controller.apply(ThermalProfile.BALANCED)

    assert result.changed is True
    assert result.verified is True
    assert result.previous_profile is ThermalProfile.QUIET
    assert result.current_profile is ThermalProfile.BALANCED
    assert profile_path.read_text(encoding="utf-8").strip() == "balanced"


def test_same_profile_is_idempotent(tmp_path: Path) -> None:
    controller, profile_path = _controller(tmp_path)

    result = controller.apply("quiet")

    assert result.changed is False
    assert result.current_profile is ThermalProfile.QUIET
    assert profile_path.read_text(encoding="utf-8").strip() == "quiet"


def test_rejects_profile_not_exposed_by_kernel(tmp_path: Path) -> None:
    controller, profile_path = _controller(
        tmp_path,
        choices="quiet balanced",
    )

    with pytest.raises(ValidationError):
        controller.apply("performance")

    assert profile_path.read_text(encoding="utf-8").strip() == "quiet"


def test_verification_failure_rolls_back(tmp_path: Path) -> None:
    def misapply(path: Path, value: str) -> None:
        profile = value.strip()
        if profile == "performance":
            path.write_text("balanced\n", encoding="utf-8")
        else:
            path.write_text(value, encoding="utf-8")

    controller, profile_path = _controller(
        tmp_path,
        write_text=misapply,
    )

    with pytest.raises(StateVerificationError) as captured:
        controller.apply("performance")

    assert captured.value.details["rollback_verified"] is True
    assert profile_path.read_text(encoding="utf-8").strip() == "quiet"


def test_rollback_failure_is_reported(tmp_path: Path) -> None:
    def broken_writer(path: Path, value: str) -> None:
        del value
        path.write_text("balanced\n", encoding="utf-8")

    controller, profile_path = _controller(
        tmp_path,
        write_text=broken_writer,
    )

    with pytest.raises(RollbackError):
        controller.apply("performance")

    assert profile_path.read_text(encoding="utf-8").strip() == "balanced"
