"""PowerDeck user-session agent entry point."""

from powerdeck_agent.session import run_forever


def main() -> int:
    run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
