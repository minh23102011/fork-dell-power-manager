"""Privileged test CLI for the transactional thermal controller."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Protocol, TextIO

from powerdeck_backends.thermal.controller import (
    PlatformProfileController,
    ThermalControlStatus,
    ThermalProfileApplyResult,
)
from powerdeck_core.errors import PowerDeckError
from powerdeck_core.models import ThermalProfile


class ThermalController(Protocol):
    def read_status(self) -> ThermalControlStatus: ...

    def apply(
        self,
        value: str | ThermalProfile,
    ) -> ThermalProfileApplyResult: ...


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="powerdeck-thermalctl",
        description=(
            "Inspect or transactionally change the kernel thermal profile."
        ),
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    get_parser = subparsers.add_parser(
        "get",
        help="Read the current and available thermal profiles.",
    )
    get_parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON.",
    )

    set_parser = subparsers.add_parser(
        "set",
        help="Apply, verify, and rollback a thermal profile.",
    )
    set_parser.add_argument(
        "profile",
        choices=tuple(profile.value for profile in ThermalProfile),
    )
    set_parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON.",
    )
    return parser


def _format_status(status: ThermalControlStatus) -> str:
    current = (
        "unknown"
        if status.current_profile is None
        else status.current_profile.value
    )
    available = (
        "none"
        if not status.available_profiles
        else ", ".join(
            profile.value for profile in status.available_profiles
        )
    )
    return "\n".join(
        (
            f"Current thermal profile: {current}",
            f"Available profiles: {available}",
            f"Source: {status.source or 'unknown'}",
            f"Path: {status.profile_path or 'unknown'}",
        )
    )


def _format_result(result: ThermalProfileApplyResult) -> str:
    action = "changed" if result.changed else "already active"
    return "\n".join(
        (
            f"Thermal profile: {result.current_profile.value}",
            f"Result: {action}",
            "Verification: passed",
            f"Previous profile: {result.previous_profile.value}",
            f"Path: {result.profile_path}",
        )
    )


def run(
    argv: Sequence[str] | None = None,
    *,
    controller: ThermalController | None = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    active_controller = (
        controller
        if controller is not None
        else PlatformProfileController()
    )

    try:
        if args.command == "get":
            status = active_controller.read_status()
            if args.json:
                print(status.to_json(indent=None), file=stdout)
            else:
                print(_format_status(status), file=stdout)
            return 0

        result = active_controller.apply(str(args.profile))
        if args.json:
            print(result.to_json(indent=None), file=stdout)
        else:
            print(_format_result(result), file=stdout)
        return 0
    except PowerDeckError as error:
        if getattr(args, "json", False):
            print(
                error.to_diagnostic().to_json(indent=None),
                file=stderr,
            )
        else:
            print(f"powerdeck-thermalctl: {error.message}", file=stderr)
            if error.hint:
                print(f"Hint: {error.hint}", file=stderr)
            if error.details:
                print(
                    json.dumps(
                        error.details,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    file=stderr,
                )
        return 1


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
