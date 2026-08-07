# PowerDeck native runtime candidate

This tree completes the native migration candidate while preserving the existing
PowerDeck D-Bus privilege boundary and rollback behavior.

## Components

- `powerdeck-core-native` — Rust transactional battery, thermal and Intel P-state control.
- `powerdeck-telemetry-native` — Rust telemetry with a tiny C `perf_event_open(2)` ABI helper.
- `powerdeckd-native` — Rust privileged system D-Bus service, Polkit-gated writes.
- `powerdeck-agent-native` — Rust user-session Battery Saver agent with ownership-aware restore.
- `qt/` — C++20 Qt6 Widgets + QtDBus unprivileged GUI.

The system daemon keeps the existing `org.powerdeck.System1` service, object path,
method signatures and JSON payload shape so old clients remain usable during the
migration. The native user agent adds `org.powerdeck.Agent1` for the Qt GUI.

The supplied systemd files are drop-ins. They do not delete the Python units;
removing the drop-ins restores the old runtime.

## Development build/install shortcuts

After all quality gates pass:

```fish
./scripts/build-release.sh
./scripts/dev-install.sh
```

The development installer keeps the original Python service units as rollback
fallbacks and only installs systemd drop-ins. To revert:

```fish
./scripts/dev-rollback.sh
```

For public distribution, the target packaging path is an Arch/CachyOS package
plus prebuilt GitHub Release artifacts so end users do not need a Python venv or
a local Rust/Qt build toolchain.
