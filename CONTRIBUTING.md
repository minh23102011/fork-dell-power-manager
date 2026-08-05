# Contributing to PowerDeck

PowerDeck controls laptop power and firmware settings. Changes must prioritize
correctness, recoverability, and explicit capability detection over convenience.

## Development rules

1. Work milestone by milestone.
2. Keep hardware access behind a backend interface.
3. Never add an arbitrary shell-command or arbitrary file-write API.
4. Never use `shell=True`.
5. Treat missing capabilities as normal, not exceptional.
6. Every mutation must support readback verification.
7. Multi-step mutations must define rollback behavior.
8. Battery Saver restore must preserve manual user changes.
9. Tests must use fake hardware by default.
10. Hardware-only tests must be explicitly marked and excluded from normal CI.

## Local checks

Using fish:

```fish
python -m venv .venv
source .venv/bin/activate.fish
python -m pip install -e ".[dev]"

ruff check .
mypy src
pytest
python -m compileall src
```

## Commit style

Use focused commits with conventional prefixes where practical:

```text
feat(core): add battery capability models
feat(battery): read Dell charging configuration
fix(transaction): reject malformed boolean fields
test(display): cover same-resolution 60 Hz selection
docs: clarify hardware safety boundary
chore: configure Ruff and Mypy
```

## Hardware reports

Sanitize reports before committing them. Remove serial numbers, UUIDs, MAC
addresses, account names, and unrelated logs.
