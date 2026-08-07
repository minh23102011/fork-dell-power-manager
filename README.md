# PowerDeck

Native Dell laptop power management for Linux, developed on CachyOS/Niri.

## Architecture

PowerDeck intentionally keeps privileged writes out of the GUI:

```text
C++20 / Qt6 GUI
         |
         | session + system D-Bus
         v
Rust user agent       Rust root daemon
         |                  |
         |                  +-- battery / thermal / Intel P-state
         |                  +-- Rust telemetry + tiny C perf helper
         |
         +-- display / brightness / power profile / keyboard / audio
```

The system API remains `org.powerdeck.System1`. Privileged writes are
Polkit-gated, verified after each write, and transactional where applicable.

## Languages

- Rust: core, daemon, agent, telemetry orchestration, CLI.
- C++20: Qt6 Widgets + QtDBus GUI.
- C: tiny `perf_event_open(2)` ABI helper.

There is no Python runtime or Python source tree in the native branch.

## Build on Arch/CachyOS

```fish
sudo pacman -S --needed rust cmake ninja qt6-base gcc pkgconf polkit

cd ~/Projects/PowerDeck
./native/scripts/native-check.sh
```

Run the source-tree GUI:

```fish
./powerdeck
```

Run the native CLI:

```fish
./native/target/release/powerdeckctl-native status
```

## Development install

After the quality gate is green:

```fish
./native/scripts/dev-install.sh
```

Then:

```fish
powerdeck
powerdeckctl status
```

## Arch package

Release packaging lives in `packaging/arch/PKGBUILD`. End users should install
a prebuilt `.pkg.tar.zst` release, or build the package with `makepkg -si`.
They do not need a Python venv.
