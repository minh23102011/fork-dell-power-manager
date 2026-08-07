# PowerDeck

<p align="center">
  <strong>Capability-driven Linux power management for Dell laptops.</strong><br>
  Verified thermal control, transactional battery charging, and ownership-aware Battery Saver automation.
</p>

<p align="center">
  <img alt="Python 3.12+" src="https://img.shields.io/badge/Python-3.12%2B-3776AB">
  <img alt="GTK4 + Libadwaita" src="https://img.shields.io/badge/UI-GTK4%20%2B%20Libadwaita-4A86CF">
  <img alt="License MIT" src="https://img.shields.io/badge/License-MIT-34D399">
  <img alt="Status v0.1 candidate" src="https://img.shields.io/badge/Status-v0.1%20candidate-6E7781">
</p>

![PowerDeck retained GTK interface](docs/assets/powerdeck-ui.png)

PowerDeck is a small Linux power-management stack built around one rule: privileged hardware changes should be validated, applied, read back, and restored safely when something does not match the requested state.

## Interface

The standalone app now uses a retained GTK4/Libadwaita shell with a compact left navigation rail and only the three v0.1 destinations:

- **Battery** — status, charging mode, and custom charging thresholds.
- **Thermal** — current platform state and kernel thermal-profile control.
- **Battery Saver** — one direct runtime switch plus optional automation and session-level limits.

The UI deliberately avoids blur, glass, gradients, continuously animated effects, duplicated page navigation, and decorative controls. It uses native symbolic icons, a single retained `Gtk.Stack`, flat cards, and a compact status header.

### Browser demo

The repository includes a browser-only simulation that mirrors the same left-sidebar layout:

```fish
./scripts/serve-readme-demo.sh
```

Open:

```text
http://127.0.0.1:8080/README.html
```

The demo is marked **SIMULATION** and cannot access or change hardware. It never contacts `powerdeckd`.

## Current state

| Area | Current state |
|---|---|
| Thermal profiles | Verified writes through Linux `platform_profile`; tested on the target laptop |
| Battery charge discovery | Reads bracketed `charge_types`, including the active raw firmware token |
| Battery charge writes | Transactional combined-file and legacy split-file backends; real-hardware write validation is still pending |
| Battery Saver | Direct runtime switch plus optional AC transition automation |
| Restore safety | Restores only settings whose current value still matches the value PowerDeck applied |
| Privilege boundary | GTK app stays unprivileged; validated system writes go through D-Bus and Polkit |
| UI | Flat retained GTK shell with a left rail, native icons, and one page stack |
| Quality gate | Ruff, Mypy, Pytest, and compileall |

## Features

### Battery

PowerDeck reads battery capacity, health, cycle count, AC state, charge mode, and custom thresholds. The charging backend supports both common Linux layouts:

- a combined writable `charge_types` file, for example `Trickle Fast Standard Adaptive [Custom]`;
- a legacy `charge_types` choices file plus a separate writable `charge_type` file.

Firmware tokens are preserved exactly for rollback. A token such as `Fast` may map to PowerDeck's `express` mode while the original raw value remains available for verification and restore.

The write path follows:

```text
snapshot → validate → apply → read back → verify
                                  │
                                  └─ mismatch → rollback → verify rollback
```

Custom threshold updates snapshot both charging mode and thresholds so a partial write can restore the previous state.

### Thermal

PowerDeck exposes the profiles advertised by the Linux platform-profile class. On the current Dell test machine those are:

- `quiet`
- `cool`
- `balanced`
- `performance`

A requested profile is checked against the kernel choices before the privileged write. The value is read back after the write, and the previous profile is restored if verification fails.

### Battery Saver

Battery Saver has one runtime switch. It can be turned on or off manually whether the laptop is connected to AC or running on battery.

Optional automation can:

- activate when AC is unplugged;
- restore an automatically started session when AC reconnects;
- cap brightness without raising it above the current value;
- select a matching lower refresh-rate mode;
- set the OS power profile;
- set the thermal profile;
- disable Intel turbo;
- cap Intel P-state maximum performance;
- set keyboard backlight level;
- optionally mute the default audio sink.

PowerDeck keeps an ownership ledger for applied session values. A value is restored only when it still equals the value PowerDeck wrote, so a manual change made while Battery Saver is active is not blindly overwritten during restore.

## Architecture

```text
┌─────────────────────────────────────┐
│ powerdeck                            │
│ GTK4 / Libadwaita, unprivileged     │
│ retained stack + left navigation    │
└──────────────────┬──────────────────┘
                   │ system D-Bus
┌──────────────────▼──────────────────┐
│ powerdeckd                           │
│ privileged system service           │
│ Polkit + validation + verified I/O  │
│ battery / thermal / Intel P-state   │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ powerdeck-agent                      │
│ per-user systemd service            │
│ AC transitions + session controls   │
│ Niri / brightness / audio / restore │
└─────────────────────────────────────┘
```

The GUI never runs as root.

## Target platform

The current hardware baseline is:

- Dell Inspiron 15 3530;
- Intel Core i7-1355U with `intel_pstate`;
- CachyOS;
- Niri on Wayland;
- power-profiles-daemon;
- PipeWire/WirePlumber;
- internal 1920×1080 display with 120 Hz and 60 Hz modes.

PowerDeck is capability-driven, but broader laptop support has not yet been certified.

## System dependencies

PowerDeck uses both Python packages and native Linux services. `pip` does not install GTK, Libadwaita, Polkit, brightness tools, or power-profiles-daemon.

### Required on Arch/CachyOS

```fish
sudo pacman -S --needed \
    git \
    python \
    python-dbus-next \
    python-gobject \
    gtk4 \
    libadwaita \
    polkit \
    brightnessctl \
    power-profiles-daemon
```

### Optional feature dependencies

| Package/tool | Feature |
|---|---|
| `niri` | Internal-panel refresh-rate switching |
| `wireplumber` / `wpctl` | Optional audio mute and restore |

Missing optional tools do not prevent the application from opening. Only the corresponding Battery Saver action is unavailable or skipped.

## Install the local v0.1 candidate

```fish
git clone https://github.com/minh23102011/fork-dell-power-manager.git
cd fork-dell-power-manager

./scripts/check-dependencies.sh

python -m venv .venv
source .venv/bin/activate.fish
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

deactivate
./scripts/install-local-v0.1.sh
./scripts/v0.1-check.sh
./powerdeck
```

The installer configures the system daemon, system D-Bus activation, Polkit action, user agent, and desktop entry.

## Development quality gate

```fish
source .venv/bin/activate.fish
python -m ruff check .
python -m mypy src
python -m pytest
python -m compileall -q src
```

## Controlled battery verification

Battery charging is firmware-backed. Run real-hardware write tests only after the quality gate passes.

Recommended order:

1. Read the current charging state.
2. Apply a non-custom mode.
3. Confirm the bracketed active token changed in `/sys/class/power_supply/BAT0/charge_types`.
4. Restore the original charging mode.
5. Test custom thresholds last.

Do not interrupt power or reboot during a firmware-backed write. The backend verifies operations and attempts rollback, but the physical laptop remains the final integration environment.

## Repository layout

```text
src/powerdeck_core/       Models, validation, errors, transaction rules
src/powerdeck_backends/   Kernel and desktop adapters
src/powerdeck_daemon/     Privileged D-Bus service
src/powerdeck_agent/      Session automation and restore orchestration
src/powerdeck_app/        Retained GTK4 / Libadwaita application
src/powerdeck_cli/        Diagnostics and development commands
data/                     systemd, D-Bus, Polkit, desktop files
tests/                    Unit and fake-hardware tests
README.html               Interactive browser-only project/demo page
README.css                HTML overview and app-simulation styles
README.js                 Browser-only demo interactions
```

## Security model

The current local Polkit policy permits an active local session to call PowerDeck's validated privileged methods. This is practical for a single-user development laptop, but a broader public package should move to an authentication or more narrowly scoped authorization policy before release.

## Current limitations

- Dell Inspiron 15 3530 is the only real-hardware validation target.
- Battery charging writes still need controlled verification on the physical machine after the combined-`charge_types` backend change.
- Fan curves, direct fan RPM control, undervolting, RAPL tuning, and per-app rules are outside v0.1.
- The HTML demo is a simulation, not a browser control surface.
- Noctalia integration is planned after the standalone app stabilizes.

## License

MIT. See [`LICENSE`](LICENSE).
