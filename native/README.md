# PowerDeck native rewrite — Phase 1

This directory is the first native migration slice. It does not replace the
currently installed Python services yet.

## Scope

- Rust workspace with no third-party runtime dependencies.
- Native thermal platform-profile controller.
- Native Intel P-state controller.
- Native battery charge-mode and custom-threshold controller.
- Validation, read-back verification, and rollback semantics preserved from the
  current Python implementation.
- Fake-sysfs unit tests live next to each controller.

## Deliberately not switched yet

- `powerdeckd` D-Bus ownership stays on the Python implementation.
- Polkit integration stays on the Python implementation.
- Telemetry stays on the Python implementation.
- GTK UI and user agent stay unchanged.

Phase 2 will connect the Rust service to the stable `org.powerdeck.System1`
D-Bus contract, migrate the session agent, add the C++20/Qt6 GUI, then remove
the Python runtime only after parity tests pass.

## Native quality gate

```fish
cd ~/Projects/PowerDeck/native
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
cargo build --release --workspace
```

The release profile uses LTO, one codegen unit, abort-on-panic, and symbol
stripping to favor a small optimized binary once executables are added.
