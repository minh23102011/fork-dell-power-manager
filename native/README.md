# PowerDeck native

PowerDeck's runtime is native-only:

- Rust power-control core.
- Rust privileged system D-Bus daemon.
- Rust user Battery Saver agent.
- Rust telemetry plus a tiny C `perf_event_open(2)` helper.
- Rust command-line client.
- C++20 Qt6 Widgets + QtDBus GUI.

Python is not a runtime, build, test, packaging, or launcher dependency.

## Quality gate

```fish
cd ~/Projects/PowerDeck
./native/scripts/native-check.sh
```

## Build

```fish
./native/scripts/build-release.sh
```

Outputs:

- `native/target/release/powerdeckd-native`
- `native/target/release/powerdeck-agent-native`
- `native/target/release/powerdeckctl-native`
- `native/qt/build/powerdeck-native`

## Development install

```fish
./native/scripts/dev-install.sh
```

The installer places canonical native units and binaries directly. It does not
rely on Python service units or systemd drop-ins.

## CLI

```fish
powerdeckctl status
powerdeckctl status --json
powerdeckctl telemetry --json
powerdeckctl thermal get --json
powerdeckctl saver state --json
```

Write operations continue to use the stable system D-Bus interface and Polkit.
