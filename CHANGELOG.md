# Changelog

All notable changes to PowerDeck will be documented in this file.

The format is based on Keep a Changelog, and the project intends to follow
Semantic Versioning after the first public release.

## [Unreleased]

### Added

- Initial project architecture and implementation plan.
- Shared typed domain models.
- Stable JSON serialization helpers.
- Structured PowerDeck error hierarchy.
- Battery, thermal, display, CPU, audio, radio, and AC state models.
- Charge-threshold and profile validation.
- Resilient TOML configuration loading.
- Atomic configuration writes with a last-known-good backup.
- Battery Saver transaction state model.
- Restore-ownership logic that preserves manual user changes.
- Initial unit tests for core behavior.

### Security

- Established the rule that the GUI must never run as root.
- Established typed D-Bus and Polkit as the future privileged-operation path.
- Prohibited arbitrary command execution and arbitrary sysfs-write APIs.

### Not yet implemented

- Read-only hardware capability aggregation.
- Dell battery write backend.
- Kernel platform-profile write backend.
- System daemon and user-session agent.
- GTK application.
- Noctalia integration.

## [0.1.0] - Unreleased

First development release. No stable release date has been assigned.
