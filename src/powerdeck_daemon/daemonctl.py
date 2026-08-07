"""Development CLI for the PowerDeck system D-Bus service."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from typing import Any, Protocol, TextIO

from powerdeck_core.errors import PowerDeckError
from powerdeck_core.models import ThermalProfile
from powerdeck_daemon.client import SystemClient


class Client(Protocol):
    async def ping(self) -> str: ...

    async def get_telemetry_state(self) -> dict[str, Any]: ...

    async def get_thermal_state(self) -> dict[str, Any]: ...

    async def set_thermal_profile(
        self,
        profile: str,
    ) -> dict[str, Any]: ...

    def disconnect(self) -> None: ...


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="powerdeck-daemonctl",
        description="Test the PowerDeck privileged system D-Bus service.",
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    subparsers.add_parser("ping")

    telemetry = subparsers.add_parser("telemetry")
    telemetry.add_argument("--json", action="store_true")

    thermal = subparsers.add_parser("thermal")
    thermal_subparsers = thermal.add_subparsers(
        dest="thermal_command",
        required=True,
    )

    get_parser = thermal_subparsers.add_parser("get")
    get_parser.add_argument("--json", action="store_true")

    set_parser = thermal_subparsers.add_parser("set")
    set_parser.add_argument(
        "profile",
        choices=tuple(profile.value for profile in ThermalProfile),
    )
    set_parser.add_argument("--json", action="store_true")
    return parser


def _print_result(
    result: dict[str, Any],
    *,
    as_json: bool,
    stdout: TextIO,
) -> None:
    if as_json:
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            file=stdout,
        )
        return

    for key, value in result.items():
        print(
            f"{key.replace('_', ' ').title()}: {value}",
            file=stdout,
        )


async def run_async(
    argv: Sequence[str] | None = None,
    *,
    client: Client | None = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    args = build_parser().parse_args(argv)
    active_client = (
        client if client is not None else await SystemClient.connect()
    )

    try:
        if args.command == "ping":
            print(await active_client.ping(), file=stdout)
            return 0

        if args.command == "telemetry":
            result = await active_client.get_telemetry_state()
            _print_result(
                result,
                as_json=bool(args.json),
                stdout=stdout,
            )
            return 0

        if args.thermal_command == "get":
            result = await active_client.get_thermal_state()
        else:
            result = await active_client.set_thermal_profile(
                str(args.profile)
            )

        _print_result(
            result,
            as_json=bool(args.json),
            stdout=stdout,
        )
        return 0
    except PowerDeckError as error:
        print(
            f"powerdeck-daemonctl: {error.message}",
            file=stderr,
        )
        return 1
    finally:
        active_client.disconnect()


def run(
    argv: Sequence[str] | None = None,
    *,
    client: Client | None = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    return asyncio.run(
        run_async(
            argv,
            client=client,
            stdout=stdout,
            stderr=stderr,
        )
    )


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
