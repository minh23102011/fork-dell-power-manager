"""CLI for Battery Saver settings and immediate operations."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict

from powerdeck_agent.session import SessionController
from powerdeck_agent.settings import load_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="powerdeck-agentctl")
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )
    for command in ("status", "apply", "restore", "settings"):
        subparsers.add_parser(command)
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    controller = SessionController()
    if args.command == "status":
        payload = controller.status()
    elif args.command == "apply":
        payload = controller.apply_now()
    elif args.command == "restore":
        payload = controller.restore_now()
    else:
        payload = asdict(load_settings())
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
