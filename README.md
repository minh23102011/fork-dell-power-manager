# PowerDeck

PowerDeck is a Linux power-management project inspired by the useful parts of
Dell Power Manager. The first target is a Dell Inspiron 15 3530 running
CachyOS, Niri, PipeWire/WirePlumber, and power-profiles-daemon.

## Planned v0.1 scope

PowerDeck is intentionally limited to three main areas:

1. **Battery charging**
   - Adaptive, Standard, Express, Primarily AC, and Custom modes.
   - Custom charge start/end thresholds.

2. **Thermal mode**
   - Quiet, Cool, Balanced, and Performance.

3. **Battery Saver**
   - Enable automatically after AC is disconnected.
   - Lower brightness without ever raising it.
   - Switch the internal display from 120 Hz to 60 Hz when supported.
   - Restore the exact previous display mode after AC reconnects.
   - Coordinate OS power profile, thermal profile, CPU limits, keyboard
     backlight, and optional audio mute.
   - Preserve manual changes made by the user while Battery Saver is active.

The complete architecture and milestone plan is documented in [`plan.md`](plan.md).

## Current status

The repository is currently in the **foundation/read-only discovery phase**.

Implemented or being established:

- typed shared domain models;
- validation and structured errors;
- resilient TOML configuration;
- transaction and restore-ownership primitives;
- unit tests for core behavior.

Not implemented yet:

- privileged hardware writes;
- Polkit authorization;
- system and session D-Bus services;
- the complete capability scanner;
- the GTK application;
- the Noctalia integration.

Do not treat the current repository as a finished power-management tool.

## Safety boundary

Until the write milestones are explicitly implemented and reviewed, PowerDeck
must not:

- write to `/sys`;
- execute any `smbios-*-ctl --set-*` operation;
- change thermal or OS power profiles;
- change CPU turbo or performance limits;
- change brightness, refresh rate, audio, keyboard backlight, or rfkill state;
- require tests to run as root.

Hardware changes will later follow:

```text
read → validate → snapshot → apply → verify → commit
                                      └────→ rollback on failure
```

The graphical application will never run as root. Privileged operations will
be exposed through typed D-Bus methods protected by Polkit.

## Development setup

The project requires Python 3.12 or newer.

Using fish:

```fish
git clone https://github.com/minh23102011/fork-dell-power-manager.git
cd fork-dell-power-manager

python -m venv .venv
source .venv/bin/activate.fish
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Run the quality gates:

```fish
ruff check .
mypy src
pytest
python -m compileall src
```

Run only the current core tests:

```fish
pytest tests/unit
```

## Repository layout

```text
src/powerdeck_core/      Shared models, validation, config, errors, transactions
src/powerdeck_backends/  Hardware and desktop adapters
src/powerdeck_cli/       Command-line interface
src/powerdeck_daemon/    Privileged system service
src/powerdeck_agent/     User-session service and Battery Saver coordinator
src/powerdeck_app/       GTK4/Libadwaita application
tests/                   Unit, integration, and fake-hardware tests
data/                    systemd, D-Bus, Polkit, desktop, and schema files
integrations/noctalia/   Future Noctalia frontend
```

## Hardware baseline

The initial hardware audit belongs in a sanitized report such as:

```text
docs/hardware/dell-inspiron-15-3530.txt
```

Do not publish serial numbers or other unnecessary machine identifiers.

## License

PowerDeck is distributed under the MIT License. See [`LICENSE`](LICENSE).
