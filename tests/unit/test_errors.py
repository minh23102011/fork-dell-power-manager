from powerdeck_core.errors import MissingCommandError
from powerdeck_core.models import Severity


def test_error_converts_to_diagnostic() -> None:
    error = MissingCommandError(
        "wpctl was not found",
        component="audio",
        hint="Install WirePlumber.",
        details={"command": "wpctl"},
    )

    issue = error.to_diagnostic()

    assert issue.code == "missing-command"
    assert issue.severity is Severity.WARNING
    assert issue.details == {"command": "wpctl"}
