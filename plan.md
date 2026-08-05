# PowerDeck — Implementation Plan

> A Linux power-management application inspired by Dell Power Manager, initially optimized for a Dell Inspiron 15 3530 running CachyOS + Niri.

## 0. Executive decision

PowerDeck should be developed as a real software project, not kept only inside a chat.

The project should have:

- a persistent Git repository;
- a versioned implementation plan;
- a hardware capability report;
- a CLI before the GUI;
- an isolated system daemon for privileged operations;
- a user-session agent for Niri, audio, brightness, and automatic restore;
- a GTK4/Libadwaita application;
- a Noctalia integration only after the standalone application is stable.

The first release must remain deliberately narrow. It contains exactly three primary pages:

1. **Battery**
   - select charging mode;
   - set custom charge start/end thresholds.

2. **Thermal Mode**
   - Quiet;
   - Cool;
   - Balanced;
   - Performance.

3. **Battery Saver**
   - enable automatically when AC is disconnected;
   - lower brightness without ever increasing it;
   - switch the internal display from 120 Hz to 60 Hz;
   - restore the prior display mode when AC returns;
   - select an OS power profile;
   - select a thermal mode;
   - optionally disable CPU turbo;
   - optionally cap CPU performance;
   - turn off keyboard backlight;
   - optionally mute audio;
   - restore only values that PowerDeck itself still owns.

The first release must not include Peak Shift, fan curves, undervolting, per-application rules, AI optimization, or broad multi-vendor support.

---

# 1. Validated target hardware

Source report: `powerdeck-capabilities.txt`

## 1.1 Machine

- Vendor: Dell Inc.
- Model: Dell Inspiron 15 3530
- Product SKU: `0C31`
- Board: `0R46N0`
- BIOS: Dell `1.30.0`
- CPU: Intel Core i7-1355U
- OS: CachyOS
- Kernel at audit time: `7.1.5-1-cachyos`

## 1.2 CPU and power driver

- `intel_pstate` is active.
- Available governors: `performance`, `powersave`.
- CPU frequency range reported by the kernel:
  - minimum: 400 MHz;
  - maximum: 5.0 GHz.
- Turbo state is exposed through:
  - `/sys/devices/system/cpu/intel_pstate/no_turbo`

The implementation must prefer `intel_pstate` policy controls over forcing a fixed MHz value.

## 1.3 Battery charging capabilities

Current state:

- charging mode: `custom`;
- charging interval: `50% → 80%`.

Available firmware charging modes:

- Adaptive;
- Standard;
- Express;
- Primarily AC;
- Custom.

Kernel battery information includes:

- `charge_types`;
- `charge_control_start_threshold`;
- `charge_control_end_threshold`;
- battery cycle count;
- charge values;
- voltage;
- temperature.

The first Dell backend should use `smbios-battery-ctl` for changing Dell charging modes and custom intervals, then verify the result through both Dell SMBIOS output and kernel-exposed battery state where possible.

Direct sysfs writes may be supported later only after the capability detector proves the relevant node is writable.

## 1.4 Thermal profile capabilities

Kernel exposes the Dell platform profile through:

- `/sys/class/platform-profile/platform-profile-0/choices`
- `/sys/class/platform-profile/platform-profile-0/profile`

Compatibility paths also exist:

- `/sys/firmware/acpi/platform_profile_choices`
- `/sys/firmware/acpi/platform_profile`

Supported values:

- `cool`;
- `quiet`;
- `balanced`;
- `performance`.

Current value at audit time:

- `balanced`.

Provider:

- `dell-pc`.

`smbios-thermal-ctl` currently fails with an SMI execution error. PowerDeck must therefore use the kernel `platform_profile` interface, not `smbios-thermal-ctl`, on this machine.

## 1.5 Existing power manager

- `power-profiles-daemon` is active.
- TLP is inactive.
- Tuned is inactive.
- auto-cpufreq is inactive.

PowerDeck must not enable a second competing power manager in v0.1.

## 1.6 Display and session controls

Internal display:

- connector: `eDP-1` at audit time;
- resolution: `1920×1080`;
- modes:
  - `120.003 Hz`;
  - `60.012 Hz`.

The code must not permanently hardcode `eDP-1`. It must discover the internal output and verify that a suitable 60 Hz mode exists.

Other validated controls:

- Intel display backlight is available.
- Dell keyboard backlight exists with values `0`, `1`, `2`.
- PipeWire/WirePlumber is available through `wpctl`.
- Bluetooth and Wi-Fi are visible through `rfkill`.
- AC state is available at `/sys/class/power_supply/AC/online`.

---

# 2. Product scope

## 2.1 Product name

Working name:

- **PowerDeck**

Executable names:

- `powerdeck` — graphical application;
- `powerdeckctl` — CLI;
- `powerdeckd` — system daemon;
- `powerdeck-agent` — user-session service.

D-Bus names:

- `org.powerdeck.System1`
- `org.powerdeck.Agent1`

Application ID:

- `org.powerdeck.PowerDeck`

## 2.2 Target user experience

The standalone application should resemble a modern OEM power-management utility:

- three clearly separated pages;
- no terminal knowledge required;
- no GUI process running as root;
- changes verified after application;
- explicit unsupported-state messaging;
- automatic restore after reconnecting AC;
- safe rollback on partial failures.

The first target platform is:

- Dell Inspiron 15 3530;
- CachyOS/Arch;
- Niri;
- PipeWire/WirePlumber;
- power-profiles-daemon.

The backend interfaces must still be vendor-neutral enough to add Lenovo, ASUS, Framework, and other machines later.

---

# 3. High-level architecture

```text
┌────────────────────────────────────────────┐
│ PowerDeck GTK4 / Libadwaita application    │
│ - Battery page                             │
│ - Thermal page                             │
│ - Battery Saver page                       │
└─────────────────────┬──────────────────────┘
                      │ Session D-Bus
                      ▼
┌────────────────────────────────────────────┐
│ powerdeck-agent                            │
│ User systemd service                       │
│                                            │
│ - monitors AC connect/disconnect events    │
│ - controls Niri display modes              │
│ - controls brightness                      │
│ - controls PipeWire audio                  │
│ - controls keyboard backlight              │
│ - coordinates Battery Saver transactions  │
│ - saves snapshots and restores state       │
└─────────────────────┬──────────────────────┘
                      │ System D-Bus
                      ▼
┌────────────────────────────────────────────┐
│ powerdeckd                                 │
│ System daemon                              │
│                                            │
│ - Dell battery charging controls           │
│ - platform_profile controls                │
│ - intel_pstate controls                    │
│ - privileged read/apply/verify operations  │
│ - Polkit authorization                     │
└────────────────────────────────────────────┘

┌────────────────────────────────────────────┐
│ powerdeckctl                               │
│ CLI for diagnostics, tests and scripting  │
└────────────────────────────────────────────┘
```

## 3.1 Why both a system daemon and user agent are required

A root system daemon is appropriate for:

- writing battery charging settings;
- writing platform profile settings;
- changing Intel P-state controls;
- enforcing authorization;
- preventing arbitrary root command execution.

A user-session process is appropriate for:

- Niri IPC;
- session D-Bus;
- PipeWire/WirePlumber;
- current output discovery;
- desktop notifications;
- brightness interaction;
- user runtime state;
- restoration after AC reconnect.

Neither process should attempt to absorb the other process’s responsibilities.

---

# 4. Technology stack

## 4.1 v0.1

- Python 3.12+
- GTK4
- Libadwaita
- PyGObject
- `dbus-next`
- `pyudev`
- TOML configuration
- JSON runtime transaction state
- pytest
- pytest-asyncio
- Ruff
- Mypy
- systemd
- Polkit

## 4.2 Packaging target

Initial package target:

- Arch Linux / CachyOS `PKGBUILD`.

Potential later targets:

- Fedora RPM;
- Debian package;
- Flatpak only for the GUI, while privileged services remain host packages.

The first version should not be Flatpak-first because the application must integrate deeply with host hardware, system D-Bus, Polkit, sysfs, Niri IPC, and systemd services.

---

# 5. Core architecture rules

## 5.1 Capability-driven behavior

No GUI option may be displayed solely because the developers expect the machine to support it.

Every control must be backed by runtime capability detection.

Example model:

```python
@dataclass(frozen=True)
class PowerDeckCapabilities:
    charging_modes: tuple[ChargeMode, ...]
    custom_charge_thresholds: bool
    thermal_profiles: tuple[ThermalProfile, ...]
    brightness_control: bool
    refresh_rate_switch: bool
    keyboard_backlight_levels: tuple[int, ...]
    audio_control: bool
    cpu_turbo_control: bool
    cpu_max_perf_control: bool
    ac_monitoring: bool
```

## 5.2 Read → validate → apply → verify

Every write must follow this flow:

1. read the current state;
2. validate the requested state;
3. create a transaction snapshot;
4. apply the change;
5. read back the result;
6. compare actual and desired values;
7. commit the transaction;
8. otherwise rollback.

An exit code of zero alone is not proof that firmware state changed.

## 5.3 No GUI `sudo`

The graphical application must never:

- launch `sudo`;
- request a password in a custom dialog;
- write directly to privileged sysfs nodes;
- run as root.

All privileged operations flow through:

```text
GUI / CLI
→ D-Bus
→ Polkit
→ powerdeckd
→ validated backend
```

## 5.4 No generic command execution API

The daemon must expose typed methods such as:

- `SetChargeMode("custom")`;
- `SetCustomChargeInterval(50, 80)`;
- `SetThermalProfile("quiet")`;
- `SetCpuPolicy({...})`.

It must never expose:

- `RunCommand(command: str)`;
- arbitrary shell execution;
- arbitrary file write paths.

## 5.5 Atomic configuration writes

Configuration updates must use:

1. write temporary file;
2. flush;
3. fsync where appropriate;
4. atomic rename;
5. preserve a last-known-good backup.

## 5.6 Manual-change preservation

When Battery Saver is active, the user may manually change brightness, volume, thermal profile, or other settings.

On restore, PowerDeck should restore a setting only when:

```text
current_value == value_applied_by_powerdeck
```

If the user changed the value after PowerDeck applied it, the user’s new value wins.

---

# 6. Domain models

## 6.1 Charging

```python
class ChargeMode(StrEnum):
    ADAPTIVE = "adaptive"
    STANDARD = "standard"
    EXPRESS = "express"
    PRIMARILY_AC = "primarily_ac"
    CUSTOM = "custom"
```

```python
@dataclass(frozen=True)
class ChargeInterval:
    start_percent: int
    end_percent: int
```

Validation:

- start: 50–95;
- end: 55–100;
- end must be at least start + 5.

```python
@dataclass(frozen=True)
class ChargeState:
    mode: ChargeMode
    interval: ChargeInterval | None
    capacity_percent: int | None
    status: str | None
    cycle_count: int | None
    temperature_celsius: float | None
```

## 6.2 Thermal

```python
class ThermalProfile(StrEnum):
    QUIET = "quiet"
    COOL = "cool"
    BALANCED = "balanced"
    PERFORMANCE = "performance"
```

```python
@dataclass(frozen=True)
class ThermalState:
    available_profiles: tuple[ThermalProfile, ...]
    current_profile: ThermalProfile
    temperatures: dict[str, float]
```

## 6.3 Battery Saver

```python
@dataclass(frozen=True)
class DisplaySaverConfig:
    brightness_cap_percent: int | None
    only_lower_brightness: bool
    target_refresh_rate_hz: float | None
    restore_refresh_rate: bool
```

```python
@dataclass(frozen=True)
class PerformanceSaverConfig:
    power_profile: str | None
    thermal_profile: ThermalProfile | None
    disable_turbo: bool
    max_perf_percent: int | None
```

```python
@dataclass(frozen=True)
class DeviceSaverConfig:
    keyboard_backlight_level: int | None
    mute_audio: bool
    disable_bluetooth: bool
    disable_wifi: bool
```

```python
@dataclass(frozen=True)
class BatterySaverConfig:
    enabled: bool
    auto_enable_on_battery: bool
    restore_on_ac: bool
    rollback_on_failure: bool
    display: DisplaySaverConfig
    performance: PerformanceSaverConfig
    devices: DeviceSaverConfig
```

---

# 7. Page 1 — Battery

## 7.1 UI sections

### Battery overview

Display:

- current battery percentage;
- charging/discharging/not-charging state;
- health when calculable;
- cycle count;
- temperature;
- current charging mode;
- current charging interval.

Example:

```text
Battery                         79%
Status                          Not charging
Health                          100%
Cycle count                     42
Temperature                     31.9°C
Charging mode                   Custom
Charging interval               50% → 80%
```

Health calculation must not be shown as authoritative when design/full capacity values are absent or clearly unreliable.

### Charging mode selector

Modes:

- Adaptive;
- Standard;
- Express;
- Primarily AC;
- Custom.

Each option should include a short explanation.

### Custom charge limits

Controls:

- start charging below;
- stop charging at.

The two values must be validated together.

### Presets

Suggested UI presets:

| Preset | Actual firmware configuration |
|---|---|
| Battery Care | Custom 50–80 |
| Mixed Use | Custom 60–90 |
| Full Capacity | Standard |
| Mostly Plugged In | Primarily AC |
| Smart Charging | Adaptive |
| Fast Charging | Express |

Presets are UI conveniences only. Persist the actual firmware mode and interval, not an invented hidden mode.

## 7.2 Backend strategy

Primary write backend:

- `DellSmbiosChargeBackend`.

Read/verification sources:

- `smbios-battery-ctl --get-charging-cfg`;
- `/sys/class/power_supply/BAT*/charge_types`;
- `/sys/class/power_supply/BAT*/charge_control_start_threshold`;
- `/sys/class/power_supply/BAT*/charge_control_end_threshold`.

Backend protocol:

```python
class ChargeBackend(Protocol):
    async def probe(self) -> ChargeCapabilities: ...
    async def get_state(self) -> ChargeState: ...
    async def set_mode(self, mode: ChargeMode) -> ChargeState: ...
    async def set_custom_interval(
        self,
        interval: ChargeInterval,
    ) -> ChargeState: ...
```

## 7.3 Write transaction

Example: apply `Custom 60–85`.

1. Read original mode and interval.
2. Validate 60 and 85.
3. Set charging mode to Custom.
4. Set custom interval.
5. Read firmware state.
6. Read sysfs thresholds.
7. Verify that mode and interval match.
8. Commit.
9. If verification fails, restore the original mode and interval.

## 7.4 Timeouts and failures

Every SMBIOS subprocess must have:

- a hard timeout;
- stdout/stderr capture;
- explicit locale handling where parsing depends on text;
- structured error mapping;
- no shell invocation.

The code must distinguish:

- permission denied;
- unsupported firmware token;
- command missing;
- timeout;
- firmware write rejected;
- readback mismatch.

---

# 8. Page 2 — Thermal Mode

## 8.1 UI

Options:

### Quiet

- prioritizes lower fan noise;
- performance may decrease;
- surface temperature may not always be the lowest.

### Cool

- prioritizes cooler surface temperature;
- fan activity may increase;
- performance may decrease.

### Balanced

- balances performance, temperature, and fan behavior.

### Performance

- prioritizes performance;
- temperature and fan noise may increase.

Display:

- current profile;
- available profiles;
- CPU temperature;
- optional skin and memory thermal readings.

## 8.2 Backend

Use:

- `KernelPlatformProfileBackend`.

Probe:

```text
/sys/class/platform-profile/platform-profile-*/choices
```

Read/write:

```text
/sys/class/platform-profile/platform-profile-*/profile
```

Fallback compatibility paths:

```text
/sys/firmware/acpi/platform_profile_choices
/sys/firmware/acpi/platform_profile
```

Do not use `smbios-thermal-ctl` on the validated target because the audit shows it is blocked/failing while the kernel interface is fully functional.

Backend protocol:

```python
class ThermalBackend(Protocol):
    async def probe(self) -> ThermalCapabilities: ...
    async def get_state(self) -> ThermalState: ...
    async def set_profile(
        self,
        profile: ThermalProfile,
    ) -> ThermalState: ...
```

## 8.3 Coordination with power-profiles-daemon

`power-profiles-daemon` may write the same platform profile.

PowerDeck must centralize profile changes in a `ProfileCoordinator`.

Suggested application order:

1. set the OS power profile;
2. wait for D-Bus confirmation;
3. set the requested thermal profile;
4. apply optional Intel P-state limits;
5. read all states again;
6. verify final state.

The Battery Saver engine, Thermal page, CLI, and future Noctalia plugin must all go through this coordinator.

---

# 9. Page 3 — Battery Saver

## 9.1 Purpose

Battery Saver is not just a wrapper around `power-saver`.

It is a transaction-based policy that combines:

- AC state;
- display brightness;
- display refresh rate;
- OS power profile;
- Dell thermal profile;
- Intel P-state limits;
- keyboard backlight;
- optional audio mute;
- optional radio controls;
- restore and rollback behavior.

## 9.2 Main UI

```text
Battery Saver

Enable automatically when unplugged        [ON]
Restore settings when plugged in            [ON]

Status
AC connected
Battery Saver waiting
```

When active:

```text
Battery Saver active

Applied
✓ Brightness limited to 40%
✓ Display switched to 60 Hz
✓ OS profile set to Power Saver
✓ Thermal profile set to Quiet
✓ CPU Turbo disabled
✓ CPU performance capped to 60%
✓ Keyboard backlight disabled
```

## 9.3 Display controls

Settings:

- brightness cap;
- only lower brightness;
- target battery refresh rate;
- restore prior refresh rate.

Brightness rule:

```text
target = min(current_brightness, configured_cap)
```

Examples:

| Before unplug | Cap | Applied |
|---:|---:|---:|
| 80% | 40% | 40% |
| 50% | 40% | 40% |
| 30% | 40% | 30% |
| 10% | 40% | 10% |

PowerDeck must never raise brightness when enabling Battery Saver.

### Refresh-rate switching

At activation:

1. discover the internal display;
2. read its current mode;
3. find a compatible 60 Hz mode with the same resolution;
4. save the exact previous mode;
5. apply the 60 Hz mode;
6. read back Niri output state;
7. verify.

At restore:

- restore the exact previous mode only when the current mode is still the one applied by PowerDeck.

## 9.4 Performance controls

Settings:

- OS power profile;
- thermal profile;
- disable turbo;
- maximum CPU performance percentage.

Default proposed battery policy:

```text
OS power profile      power-saver
Thermal profile       quiet
Disable turbo         enabled
Max performance       60%
```

The final defaults should be benchmarked before release.

### Intel P-state

Potential nodes:

- `/sys/devices/system/cpu/intel_pstate/no_turbo`
- `/sys/devices/system/cpu/intel_pstate/max_perf_pct`
- `/sys/devices/system/cpu/intel_pstate/min_perf_pct`

The capability scanner must confirm each file exists and is writable before exposing its control.

Do not force a fixed CPU frequency.

## 9.5 Device controls

Settings:

- keyboard backlight level;
- mute speakers;
- disable Bluetooth;
- disable Wi-Fi.

Safe defaults:

- keyboard backlight: off;
- mute speakers: off;
- Bluetooth: unchanged;
- Wi-Fi: unchanged.

Wi-Fi and Bluetooth disabling must remain opt-in.

## 9.6 Trigger and AC monitoring

Source:

```text
/sys/class/power_supply/AC/online
```

Monitoring mechanism:

- `pyudev` event subscription;
- fallback periodic reconciliation at a low frequency;
- no tight polling loop.

Transitions:

```text
AC 1 → 0
activate Battery Saver

AC 0 → 1
restore previous state
```

Debounce rapid AC events to avoid repeated apply/restore loops.

---

# 10. Battery Saver transaction engine

## 10.1 State machine

```text
IDLE
  │ AC disconnected
  ▼
SNAPSHOTTING
  ▼
PLANNING
  ▼
APPLYING
  ├── success ──► ACTIVE
  └── failure ──► ROLLING_BACK ──► IDLE / ERROR

ACTIVE
  │ AC connected
  ▼
RESTORING
  ├── success ──► IDLE
  └── failure ──► ERROR
```

## 10.2 Snapshot format

Runtime location:

```text
$XDG_RUNTIME_DIR/powerdeck/active-transaction.json
```

Persistent recovery location may be added when needed:

```text
$XDG_STATE_HOME/powerdeck/recovery.json
```

Example:

```json
{
  "schema_version": 1,
  "transaction_id": "UUID",
  "trigger": "ac-disconnected",
  "started_at": "ISO-8601",
  "before": {
    "brightness_percent": 72,
    "display_mode": "1920x1080@120.003",
    "audio_volume": 0.55,
    "audio_muted": false,
    "keyboard_backlight": 1,
    "power_profile": "balanced",
    "thermal_profile": "balanced",
    "cpu_no_turbo": 0,
    "cpu_max_perf_pct": 100
  },
  "applied": {
    "brightness_percent": 40,
    "display_mode": "1920x1080@60.012",
    "audio_muted": false,
    "keyboard_backlight": 0,
    "power_profile": "power-saver",
    "thermal_profile": "quiet",
    "cpu_no_turbo": 1,
    "cpu_max_perf_pct": 60
  }
}
```

## 10.3 Restore ownership rule

For each setting:

```text
if current == applied_by_powerdeck:
    restore(before)
else:
    preserve(current)
```

This protects manual user changes.

## 10.4 Apply ordering

Suggested order:

1. snapshot all available settings;
2. lower brightness;
3. switch refresh rate;
4. set OS power profile;
5. set thermal profile;
6. apply turbo/performance caps;
7. change keyboard backlight;
8. optionally mute audio;
9. optionally change Bluetooth/Wi-Fi;
10. verify all settings;
11. mark transaction active.

## 10.5 Restore ordering

Suggested reverse order:

1. restore optional radios;
2. restore audio when PowerDeck still owns mute state;
3. restore keyboard backlight;
4. restore CPU controls;
5. restore thermal profile;
6. restore OS power profile;
7. restore refresh rate;
8. restore brightness;
9. verify;
10. remove active transaction.

## 10.6 Rollback behavior

v0.1 default:

- any required step failure causes rollback of all successfully applied steps.

Optional settings such as Bluetooth can be marked non-critical only after the initial release proves the transaction model is stable.

## 10.7 Crash recovery

On agent startup:

1. load active transaction if present;
2. read current AC state;
3. if AC is connected, attempt safe restore;
4. if AC is disconnected, reconcile active policy;
5. if the snapshot is malformed, preserve current state and show a diagnostic warning;
6. never guess unknown original values.

---

# 11. Backends

## 11.1 Battery

- `DellSmbiosChargeBackend`
- `SysfsBatteryReader`
- future `SysfsChargeBackend`

## 11.2 Thermal

- `KernelPlatformProfileBackend`

## 11.3 CPU

- `IntelPstateBackend`
- future generic `CpuFreqBackend`

## 11.4 OS power profiles

- `PowerProfilesDaemonBackend`

Use D-Bus rather than parsing CLI output when feasible.

## 11.5 Display

- `NiriDisplayBackend`

Responsibilities:

- query outputs;
- detect internal display;
- parse available modes;
- apply a selected mode;
- verify current mode.

## 11.6 Brightness

- `BrightnessctlBackend` for v0.1;
- optional direct backlight sysfs implementation later.

## 11.7 Audio

- `WirePlumberBackend`

Responsibilities:

- read default sink volume and mute state;
- set mute;
- restore only when PowerDeck still owns the applied state.

## 11.8 Keyboard backlight

- `LedClassKeyboardBacklightBackend`

Discover:

```text
/sys/class/leds/*kbd_backlight*
```

## 11.9 Radio

- `RfkillBackend`

Radio changes remain disabled by default.

---

# 12. D-Bus design

## 12.1 System daemon

Bus name:

```text
org.powerdeck.System
```

Object path:

```text
/org/powerdeck/System
```

Interface:

```text
org.powerdeck.System1
```

Methods:

```text
GetCapabilities() -> a{sv}
GetBatteryState() -> a{sv}
SetChargeMode(s mode) -> a{sv}
SetCustomChargeInterval(i start, i end) -> a{sv}

GetThermalState() -> a{sv}
SetThermalProfile(s profile) -> a{sv}

GetCpuPolicy() -> a{sv}
SetCpuPolicy(a{sv} policy) -> a{sv}
RestoreCpuPolicy(a{sv} snapshot) -> a{sv}
```

Signals:

```text
BatteryStateChanged(a{sv})
ThermalStateChanged(a{sv})
CpuPolicyChanged(a{sv})
OperationFailed(s code, s message)
```

## 12.2 User agent

Bus name:

```text
org.powerdeck.Agent
```

Object path:

```text
/org/powerdeck/Agent
```

Interface:

```text
org.powerdeck.Agent1
```

Methods:

```text
GetState() -> a{sv}
GetCapabilities() -> a{sv}
GetBatterySaverConfig() -> a{sv}
UpdateBatterySaverConfig(a{sv} config) -> a{sv}

PreviewBatterySaverPlan() -> a{sv}
EnableBatterySaver(s reason) -> a{sv}
DisableBatterySaver(s reason) -> a{sv}
RestoreActiveTransaction() -> a{sv}
```

Signals:

```text
StateChanged(a{sv})
AcPowerChanged(b online)
BatterySaverActivated(a{sv})
BatterySaverRestored(a{sv})
BatterySaverFailed(s code, s message)
```

---

# 13. Polkit

Actions:

```text
org.powerdeck.change-battery-charging
org.powerdeck.change-thermal-profile
org.powerdeck.change-cpu-policy
```

Rules:

- active local user may authenticate;
- no custom password storage;
- no blanket `NOPASSWD` sudoers entry;
- no arbitrary sysfs write permission;
- authorization evaluated in the daemon immediately before mutation.

The user agent should not require root for session-only actions.

---

# 14. Configuration

Path:

```text
~/.config/powerdeck/config.toml
```

Example:

```toml
schema_version = 1

[battery]
preferred_mode = "custom"
custom_start = 50
custom_end = 80

[thermal]
preferred_mode = "balanced"

[battery_saver]
enabled = true
auto_enable_on_battery = true
restore_on_ac = true
rollback_on_failure = true

[battery_saver.display]
brightness_cap_percent = 40
only_lower_brightness = true
target_refresh_rate_hz = 60.0
restore_refresh_rate = true

[battery_saver.performance]
power_profile = "power-saver"
thermal_profile = "quiet"
disable_turbo = true
max_perf_percent = 60

[battery_saver.devices]
keyboard_backlight_level = 0
mute_audio = false
disable_bluetooth = false
disable_wifi = false
```

Requirements:

- schema versioning;
- strict value validation;
- atomic save;
- last-known-good backup;
- unknown keys logged but preserved where practical;
- invalid fields do not erase the whole configuration.

---

# 15. CLI

## 15.1 General

```bash
powerdeckctl status
powerdeckctl capabilities
powerdeckctl diagnose
powerdeckctl --json status
```

## 15.2 Battery

```bash
powerdeckctl battery status
powerdeckctl battery mode adaptive
powerdeckctl battery mode standard
powerdeckctl battery mode express
powerdeckctl battery mode primarily-ac
powerdeckctl battery mode custom
powerdeckctl battery custom 50 80
```

## 15.3 Thermal

```bash
powerdeckctl thermal status
powerdeckctl thermal quiet
powerdeckctl thermal cool
powerdeckctl thermal balanced
powerdeckctl thermal performance
```

## 15.4 Battery Saver

```bash
powerdeckctl saver status
powerdeckctl saver preview
powerdeckctl saver enable
powerdeckctl saver disable
powerdeckctl saver restore
```

JSON output must be stable enough for the future Noctalia integration.

---

# 16. GTK4 / Libadwaita application

## 16.1 Window

- default size: approximately `1000×680`;
- minimum size: approximately `880×600`;
- adaptive enough for narrower layouts;
- no custom client-side glass effect in v0.1;
- use native Libadwaita patterns.

## 16.2 Navigation

Sidebar:

```text
PowerDeck

Battery
Thermal Mode
Battery Saver
```

Footer summary:

```text
Battery 79%
AC Connected
Balanced
```

## 16.3 UI behavior

Battery and Thermal options:

- apply immediately after selection;
- show progress;
- verify;
- show success/error toast.

Custom charge thresholds:

- use an explicit Apply button;
- disable Apply until validation succeeds.

Battery Saver settings:

- save immediately;
- show whether each capability is available;
- show a clear reason when unsupported.

## 16.4 Error states

Examples:

- PowerDeck daemon unavailable;
- powerdeck-agent unavailable;
- Polkit authentication cancelled;
- firmware rejected charging mode;
- 60 Hz mode unavailable;
- PipeWire unavailable;
- Niri IPC unavailable;
- CPU cap unsupported;
- verification mismatch.

The UI must never silently pretend success.

---

# 17. Repository structure

```text
powerdeck/
├── pyproject.toml
├── README.md
├── LICENSE
├── CHANGELOG.md
├── powerdeck-implementation-plan.md
├── powerdeck-capabilities.txt
│
├── src/
│   ├── powerdeck_core/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── capabilities.py
│   │   ├── errors.py
│   │   ├── config.py
│   │   ├── validation.py
│   │   ├── transactions.py
│   │   └── logging.py
│   │
│   ├── powerdeck_backends/
│   │   ├── battery/
│   │   │   ├── base.py
│   │   │   ├── dell_smbios.py
│   │   │   └── sysfs_reader.py
│   │   ├── thermal/
│   │   │   ├── base.py
│   │   │   └── platform_profile.py
│   │   ├── cpu/
│   │   │   ├── base.py
│   │   │   └── intel_pstate.py
│   │   ├── power/
│   │   │   └── power_profiles_daemon.py
│   │   ├── display/
│   │   │   ├── base.py
│   │   │   └── niri.py
│   │   ├── brightness/
│   │   │   └── brightnessctl.py
│   │   ├── audio/
│   │   │   └── wireplumber.py
│   │   ├── keyboard/
│   │   │   └── leds.py
│   │   └── radio/
│   │       └── rfkill.py
│   │
│   ├── powerdeck_daemon/
│   │   ├── main.py
│   │   ├── dbus_service.py
│   │   ├── authorization.py
│   │   └── hardware_manager.py
│   │
│   ├── powerdeck_agent/
│   │   ├── main.py
│   │   ├── dbus_service.py
│   │   ├── ac_monitor.py
│   │   ├── saver_engine.py
│   │   ├── profile_coordinator.py
│   │   └── restore_manager.py
│   │
│   ├── powerdeck_cli/
│   │   ├── main.py
│   │   └── commands/
│   │
│   └── powerdeck_app/
│       ├── main.py
│       ├── application.py
│       ├── window.py
│       ├── pages/
│       │   ├── battery.py
│       │   ├── thermal.py
│       │   └── battery_saver.py
│       ├── widgets/
│       └── style.css
│
├── data/
│   ├── systemd/
│   │   ├── powerdeckd.service
│   │   └── powerdeck-agent.service
│   ├── dbus/
│   ├── polkit/
│   ├── desktop/
│   ├── icons/
│   └── schemas/
│
├── integrations/
│   └── noctalia/
│
├── packaging/
│   └── arch/
│       └── PKGBUILD
│
└── tests/
    ├── unit/
    ├── integration/
    ├── fixtures/
    └── fake_sysfs/
```

---

# 18. Milestones

## Milestone 0 — Repository foundation

Deliverables:

- Python package scaffold;
- `pyproject.toml`;
- Ruff configuration;
- Mypy configuration;
- pytest configuration;
- basic logging;
- core error hierarchy;
- typed domain models;
- CI for Python 3.12 and 3.13;
- development documentation.

Gates:

```bash
ruff check .
mypy src
pytest
python -m compileall src
```

All pass.

No privileged writes. No GUI.

## Milestone 1 — Read-only capability scanner

Deliverables:

- machine identification;
- battery reader;
- Dell charge capability detection;
- thermal profile detection;
- Intel P-state detection;
- power-profiles-daemon detection;
- Niri output parser;
- brightness detection;
- keyboard backlight detection;
- PipeWire detection;
- AC state detection;
- structured `powerdeckctl capabilities`;
- structured `powerdeckctl status`;
- fake sysfs fixtures.

Acceptance on target machine:

- identifies Inspiron 15 3530;
- detects Custom 50–80;
- detects all four thermal modes;
- detects 120/60 Hz;
- detects keyboard backlight 0–2;
- detects `intel_pstate`;
- performs no hardware writes.

## Milestone 2 — Battery control

Deliverables:

- `DellSmbiosChargeBackend`;
- charge mode changes;
- custom threshold changes;
- validation;
- apply/verify/rollback;
- system daemon skeleton;
- Polkit battery action;
- CLI battery commands.

Acceptance:

- all supported charging modes work;
- invalid thresholds are rejected;
- readback is verified;
- rollback occurs on mismatch;
- reboot preserves firmware setting.

## Milestone 3 — Thermal control

Deliverables:

- `KernelPlatformProfileBackend`;
- temperature reader;
- thermal D-Bus methods;
- Polkit thermal action;
- CLI thermal commands.

Acceptance:

- all four modes work;
- unsupported values are rejected;
- no use of `smbios-thermal-ctl`;
- readback matches requested value.

## Milestone 4 — User-session backends

Deliverables:

- Niri output backend;
- brightness backend;
- audio backend;
- keyboard backlight backend;
- power-profiles-daemon backend;
- Intel P-state backend;
- AC event monitor.

Acceptance:

- manual CLI preview works;
- 120 → 60 and 60 → 120 restore works;
- brightness cap works;
- audio and keyboard state can be snapshot/restored;
- no automatic AC trigger yet.

## Milestone 5 — Battery Saver transaction engine

Deliverables:

- snapshot model;
- apply plan;
- verification;
- rollback;
- restore;
- manual-change protection;
- crash recovery;
- AC auto-trigger;
- structured event logs.

Acceptance:

- unplug activates;
- plug restores;
- manual brightness/volume changes are preserved;
- failed steps rollback;
- agent restart recovers safely.

## Milestone 6 — GTK application

Deliverables:

- Battery page;
- Thermal page;
- Battery Saver page;
- capability-aware UI;
- asynchronous D-Bus calls;
- Polkit flow;
- progress and error states;
- diagnostics dialog.

Acceptance:

- GUI runs unprivileged;
- no UI freeze;
- no false success;
- all three pages work on target hardware.

## Milestone 7 — Hardening

Scenarios:

- repeated unplug/plug;
- suspend/resume;
- daemon restart;
- agent restart;
- Niri restart;
- PipeWire restart;
- output mode missing;
- Polkit cancellation;
- SMBIOS timeout;
- readback mismatch;
- external profile changes;
- malformed config;
- malformed transaction state.

Deliverables:

- stable error codes;
- timeout policy;
- recovery logic;
- diagnostic bundle;
- migration support.

## Milestone 8 — Arch packaging

Deliverables:

- `PKGBUILD`;
- system daemon unit;
- user agent unit;
- D-Bus service files;
- Polkit policy;
- desktop entry;
- application icon;
- install/uninstall documentation.

## Milestone 9 — Noctalia integration

Only after the standalone app is stable.

Plugin scope:

- compact bar indicator;
- Battery Saver toggle;
- thermal mode selector;
- charging summary;
- button to open PowerDeck.

The plugin must not write hardware directly.

---

# 19. Testing strategy

## 19.1 Unit tests

Required coverage:

- threshold boundaries;
- enum parsing;
- config parsing;
- atomic config save;
- snapshot serialization;
- restore ownership rule;
- thermal profile parsing;
- Intel P-state capability detection;
- Niri output parsing;
- 60 Hz mode selection;
- brightness cap behavior;
- missing file behavior;
- command timeout behavior;
- error mapping.

## 19.2 Fake sysfs

```text
tests/fake_sysfs/
├── class/
│   ├── power_supply/
│   ├── platform-profile/
│   ├── backlight/
│   └── leds/
├── devices/system/cpu/intel_pstate/
└── firmware/acpi/
```

CI must never write to real host sysfs.

## 19.3 Integration tests

Use fake adapters for:

- SMBIOS command execution;
- D-Bus;
- Niri output responses;
- brightnessctl;
- wpctl;
- rfkill;
- power-profiles-daemon.

## 19.4 Hardware test checklist

Battery:

- Adaptive;
- Standard;
- Express;
- Primarily AC;
- Custom 50–80;
- Custom 60–90;
- invalid thresholds rejected.

Thermal:

- Quiet;
- Cool;
- Balanced;
- Performance.

Battery Saver:

- brightness cap;
- 120 → 60;
- 60 → previous mode;
- power profile apply/restore;
- thermal mode apply/restore;
- turbo apply/restore;
- performance cap apply/restore;
- keyboard backlight apply/restore;
- optional mute apply/restore;
- manual override preservation;
- unplug/plug debounce;
- suspend/resume;
- crash recovery.

---

# 20. Security requirements

- no GUI root mode;
- no stored passwords;
- no wide sudoers rule;
- no arbitrary command D-Bus method;
- no arbitrary file-write method;
- input validation at both client and daemon;
- subprocesses run without shell;
- fixed executable paths or verified command discovery;
- strict timeout;
- structured authorization errors;
- Polkit authorization per privileged operation class;
- atomic state writes;
- safe behavior when capability disappears at runtime.

---

# 21. Performance requirements

- no polling faster than necessary;
- AC state primarily event-driven;
- battery state refresh every several seconds, not every frame;
- thermal data refresh approximately every 1–3 seconds while visible;
- GUI must not block on hardware operations;
- daemon idle CPU usage should be negligible;
- agent should not continuously invoke `niri msg`, `wpctl`, or SMBIOS tools without a reason;
- historical graphs are excluded from v0.1.

---

# 22. Out of scope for v0.1

- Peak Shift;
- Advanced Charge scheduling;
- fan curves;
- direct fan RPM control;
- undervolting;
- Intel RAPL power limits;
- automatic Wi-Fi disable by default;
- per-application profiles;
- game detection;
- AI optimization;
- cloud synchronization;
- long-term SQLite history;
- multi-vendor production support;
- a full Noctalia plugin;
- custom compositor glass effects.

---

# 23. Definition of done for v0.1

## Battery

- reads current mode;
- exposes supported modes;
- applies all validated Dell charging modes;
- applies valid custom thresholds;
- verifies state;
- rolls back on failure.

## Thermal

- reads supported profiles;
- applies Quiet/Cool/Balanced/Performance;
- uses kernel platform profile;
- verifies state.

## Battery Saver

- auto-enables on AC disconnect;
- never raises brightness;
- switches 120 Hz to 60 Hz where available;
- restores the exact previous display mode;
- applies OS power profile;
- applies thermal profile;
- optionally disables turbo;
- optionally caps CPU performance;
- turns off keyboard backlight;
- optionally mutes audio;
- restores on AC reconnect;
- preserves manual user changes;
- rolls back partial failure;
- survives restart with safe recovery.

## Security

- GUI remains unprivileged;
- Polkit protects privileged changes;
- no arbitrary command execution;
- all inputs are validated.

## Quality

- Ruff passes;
- Mypy passes at the agreed strictness;
- pytest passes;
- compileall passes;
- hardware checklist passes on the target laptop;
- installation and recovery documentation exists.

---

# 24. Exact implementation order

```text
1. Create repository and documentation
2. Add core models and error types
3. Add fake sysfs test framework
4. Build read-only capability scanner
5. Implement powerdeckctl status/capabilities/diagnose
6. Implement Dell battery backend
7. Implement powerdeckd and Polkit
8. Implement kernel thermal backend
9. Implement user-session agent
10. Implement Niri/brightness/audio/keyboard backends
11. Implement OS power and Intel P-state coordination
12. Implement snapshot/apply/verify/restore engine
13. Add AC auto-trigger
14. Build GTK application
15. Run target-hardware integration tests
16. Harden failure and recovery paths
17. Build Arch package
18. Add Noctalia integration
```

---

# 25. First coding task

The first coding task must implement only:

- Milestone 0;
- Milestone 1.

It must not:

- write to sysfs;
- call any SMBIOS `--set-*` operation;
- change power profiles;
- change thermal profiles;
- change brightness;
- change refresh rate;
- change audio;
- create the final GTK GUI.

The first task should establish trustworthy read-only discovery before any hardware mutation is introduced.
