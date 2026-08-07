use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command as ProcessCommand;

use serde_json::{Value, json};
use zbus::proxy;

pub const SYSTEM_SERVICE: &str = "org.powerdeck.System1";
pub const SYSTEM_PATH: &str = "/org/powerdeck/System1";
pub const SYSTEM_INTERFACE: &str = "org.powerdeck.System1";
pub const AGENT_SERVICE: &str = "org.powerdeck.Agent1";
pub const AGENT_PATH: &str = "/org/powerdeck/Agent1";
pub const AGENT_INTERFACE: &str = "org.powerdeck.Agent1";

#[proxy(
    interface = "org.powerdeck.System1",
    default_service = "org.powerdeck.System1",
    default_path = "/org/powerdeck/System1"
)]
trait System {
    #[zbus(name = "Ping")]
    async fn ping(&self) -> zbus::Result<String>;

    #[zbus(name = "GetTelemetryState")]
    async fn get_telemetry_state(&self) -> zbus::Result<String>;

    #[zbus(name = "GetThermalState")]
    async fn get_thermal_state(&self) -> zbus::Result<String>;

    #[zbus(name = "SetThermalProfile")]
    async fn set_thermal_profile(&self, profile: &str) -> zbus::Result<String>;

    #[zbus(name = "GetChargeState")]
    async fn get_charge_state(&self) -> zbus::Result<String>;

    #[zbus(name = "SetChargeMode")]
    async fn set_charge_mode(&self, mode: &str) -> zbus::Result<String>;

    #[zbus(name = "SetChargeThresholds")]
    async fn set_charge_thresholds(
        &self,
        start_percent: i32,
        end_percent: i32,
    ) -> zbus::Result<String>;

    #[zbus(name = "GetCpuState")]
    async fn get_cpu_state(&self) -> zbus::Result<String>;

    #[zbus(name = "SetCpuPolicy")]
    async fn set_cpu_policy(
        &self,
        disable_turbo: bool,
        max_performance_percent: i32,
    ) -> zbus::Result<String>;
}

#[proxy(
    interface = "org.powerdeck.Agent1",
    default_service = "org.powerdeck.Agent1",
    default_path = "/org/powerdeck/Agent1"
)]
trait Agent {
    #[zbus(name = "Ping")]
    async fn ping(&self) -> zbus::Result<String>;

    #[zbus(name = "GetState")]
    async fn get_state(&self) -> zbus::Result<String>;

    #[zbus(name = "GetSettings")]
    async fn get_settings(&self) -> zbus::Result<String>;

    #[zbus(name = "SetSaverEnabled")]
    async fn set_saver_enabled(&self, enabled: bool) -> zbus::Result<String>;

    #[zbus(name = "SetSettings")]
    async fn set_settings(&self, settings_json: &str) -> zbus::Result<String>;
}

#[derive(Debug, Clone, PartialEq)]
enum CliCommand {
    Status {
        json: bool,
    },
    Ping,
    Telemetry {
        json: bool,
    },
    ChargeGet {
        json: bool,
    },
    ChargeMode {
        mode: String,
    },
    ChargeThresholds {
        start: i32,
        end: i32,
    },
    ThermalGet {
        json: bool,
    },
    ThermalSet {
        profile: String,
    },
    CpuGet {
        json: bool,
    },
    CpuSet {
        disable_turbo: bool,
        max_performance_percent: i32,
    },
    SaverState {
        json: bool,
    },
    SaverSettings {
        json: bool,
    },
    SaverEnabled {
        enabled: bool,
    },
    SaverSetSettings {
        payload: String,
    },
    Help,
}

fn usage() -> &'static str {
    r#"PowerDeck native CLI

Usage:
  powerdeckctl status [--json]
  powerdeckctl ping
  powerdeckctl telemetry [--json]
  powerdeckctl charge get [--json]
  powerdeckctl charge mode <adaptive|standard|express|custom|...>
  powerdeckctl charge thresholds <start> <end>
  powerdeckctl thermal get [--json]
  powerdeckctl thermal set <cool|quiet|balanced|performance>
  powerdeckctl cpu get [--json]
  powerdeckctl cpu set <turbo-on|turbo-off> <max-percent>
  powerdeckctl saver state [--json]
  powerdeckctl saver settings [--json]
  powerdeckctl saver on
  powerdeckctl saver off
  powerdeckctl saver set-settings '<json>'

Compatibility names:
  powerdeck-daemonctl
  powerdeck-thermalctl
  powerdeck-agentctl
"#
}

fn parse_bool_flag(value: &str) -> Result<bool, String> {
    match value {
        "true" | "1" | "yes" | "on" | "turbo-off" | "disable" | "disabled" => Ok(true),
        "false" | "0" | "no" | "off" | "turbo-on" | "enable" | "enabled" => Ok(false),
        _ => Err(format!("invalid boolean/turbo value: {value}")),
    }
}

fn parse_percent(value: &str) -> Result<i32, String> {
    let parsed = value
        .parse::<i32>()
        .map_err(|_| format!("invalid percentage: {value}"))?;
    if !(1..=100).contains(&parsed) {
        return Err("percentage must be between 1 and 100".to_owned());
    }
    Ok(parsed)
}

fn has_json_flag(args: &[String]) -> bool {
    args.iter().any(|value| value == "--json")
}

fn parse_canonical(args: &[String]) -> Result<CliCommand, String> {
    let Some(command) = args.first().map(String::as_str) else {
        return Ok(CliCommand::Status { json: false });
    };

    match command {
        "-h" | "--help" | "help" => Ok(CliCommand::Help),
        "status" => Ok(CliCommand::Status {
            json: has_json_flag(&args[1..]),
        }),
        "ping" => Ok(CliCommand::Ping),
        "telemetry" => Ok(CliCommand::Telemetry {
            json: has_json_flag(&args[1..]),
        }),
        "charge" => match args.get(1).map(String::as_str) {
            Some("get") | Some("status") => Ok(CliCommand::ChargeGet {
                json: has_json_flag(&args[2..]),
            }),
            Some("mode") => {
                let mode = args.get(2).ok_or("charge mode requires a mode")?.to_owned();
                Ok(CliCommand::ChargeMode { mode })
            }
            Some("thresholds") => {
                let start = args
                    .get(2)
                    .ok_or("charge thresholds requires start and end")?
                    .parse::<i32>()
                    .map_err(|_| "charge start threshold is not an integer")?;
                let end = args
                    .get(3)
                    .ok_or("charge thresholds requires start and end")?
                    .parse::<i32>()
                    .map_err(|_| "charge end threshold is not an integer")?;
                if !(1..=100).contains(&start) || !(1..=100).contains(&end) {
                    return Err("charge thresholds must be between 1 and 100".to_owned());
                }
                if start >= end {
                    return Err("charge start threshold must be below end threshold".to_owned());
                }
                Ok(CliCommand::ChargeThresholds { start, end })
            }
            _ => Err("charge expects get, mode, or thresholds".to_owned()),
        },
        "thermal" => match args.get(1).map(String::as_str) {
            None | Some("get") | Some("status") => Ok(CliCommand::ThermalGet {
                json: has_json_flag(&args[2..]),
            }),
            Some("set") => {
                let profile = args
                    .get(2)
                    .ok_or("thermal set requires a profile")?
                    .to_owned();
                Ok(CliCommand::ThermalSet { profile })
            }
            _ => Err("thermal expects get or set".to_owned()),
        },
        "cpu" => match args.get(1).map(String::as_str) {
            None | Some("get") | Some("status") => Ok(CliCommand::CpuGet {
                json: has_json_flag(&args[2..]),
            }),
            Some("set") => {
                let turbo = args
                    .get(2)
                    .ok_or("cpu set requires turbo-on or turbo-off")?;
                let maximum = args.get(3).ok_or("cpu set requires a maximum percentage")?;
                Ok(CliCommand::CpuSet {
                    disable_turbo: parse_bool_flag(turbo)?,
                    max_performance_percent: parse_percent(maximum)?,
                })
            }
            _ => Err("cpu expects get or set".to_owned()),
        },
        "saver" => match args.get(1).map(String::as_str) {
            None | Some("state") | Some("status") => Ok(CliCommand::SaverState {
                json: has_json_flag(&args[2..]),
            }),
            Some("settings") => Ok(CliCommand::SaverSettings {
                json: has_json_flag(&args[2..]),
            }),
            Some("on") | Some("enable") => Ok(CliCommand::SaverEnabled { enabled: true }),
            Some("off") | Some("disable") => Ok(CliCommand::SaverEnabled { enabled: false }),
            Some("set-settings") => {
                let payload = args
                    .get(2)
                    .ok_or("saver set-settings requires a JSON object")?
                    .to_owned();
                serde_json::from_str::<Value>(&payload)
                    .map_err(|error| format!("invalid settings JSON: {error}"))?;
                Ok(CliCommand::SaverSetSettings { payload })
            }
            _ => Err("saver expects state, settings, on, off, or set-settings".to_owned()),
        },
        _ => Err(format!("unknown command: {command}")),
    }
}

fn parse_compat(program: &str, args: &[String]) -> Result<CliCommand, String> {
    match program {
        "powerdeck-thermalctl" => {
            if args.first().map(String::as_str) == Some("set") {
                let profile = args
                    .get(1)
                    .ok_or("powerdeck-thermalctl set requires a profile")?
                    .to_owned();
                Ok(CliCommand::ThermalSet { profile })
            } else {
                Ok(CliCommand::ThermalGet {
                    json: has_json_flag(args),
                })
            }
        }
        "powerdeck-agentctl" => match args.first().map(String::as_str) {
            Some("settings") => Ok(CliCommand::SaverSettings {
                json: has_json_flag(&args[1..]),
            }),
            Some("enable") | Some("on") => Ok(CliCommand::SaverEnabled { enabled: true }),
            Some("disable") | Some("off") => Ok(CliCommand::SaverEnabled { enabled: false }),
            _ => Ok(CliCommand::SaverState {
                json: has_json_flag(args),
            }),
        },
        "powerdeck-daemonctl" => match args.first().map(String::as_str) {
            Some("telemetry") => Ok(CliCommand::Telemetry {
                json: has_json_flag(&args[1..]),
            }),
            Some("charge") => Ok(CliCommand::ChargeGet {
                json: has_json_flag(&args[1..]),
            }),
            Some("thermal") => Ok(CliCommand::ThermalGet {
                json: has_json_flag(&args[1..]),
            }),
            Some("cpu") => Ok(CliCommand::CpuGet {
                json: has_json_flag(&args[1..]),
            }),
            _ => Ok(CliCommand::Ping),
        },
        _ => parse_canonical(args),
    }
}

fn parse_json_payload(payload: &str) -> Value {
    serde_json::from_str(payload).unwrap_or_else(|_| json!({"raw": payload}))
}

fn print_payload(payload: &str, pretty: bool) {
    if pretty {
        let value = parse_json_payload(payload);
        match serde_json::to_string_pretty(&value) {
            Ok(text) => println!("{text}"),
            Err(_) => println!("{payload}"),
        }
    } else {
        println!("{payload}");
    }
}

fn read_trimmed(path: impl AsRef<Path>) -> Option<String> {
    fs::read_to_string(path)
        .ok()
        .map(|value| value.trim().to_owned())
}

fn read_u64(path: impl AsRef<Path>) -> Option<u64> {
    read_trimmed(path)?.parse::<u64>().ok()
}

fn os_name() -> String {
    let content = fs::read_to_string("/etc/os-release").unwrap_or_default();
    for key in ["PRETTY_NAME=", "NAME="] {
        if let Some(line) = content.lines().find(|line| line.starts_with(key)) {
            return line[key.len()..].trim_matches('"').to_owned();
        }
    }
    "Linux".to_owned()
}

fn machine_name() -> Value {
    json!({
        "vendor": read_trimmed("/sys/devices/virtual/dmi/id/sys_vendor"),
        "product": read_trimmed("/sys/devices/virtual/dmi/id/product_name"),
    })
}

fn is_laptop_battery_name(name: &str) -> bool {
    name.starts_with("BAT")
}

fn first_battery() -> Option<PathBuf> {
    let root = Path::new("/sys/class/power_supply");
    let entries = fs::read_dir(root).ok()?;
    let mut batteries = entries
        .flatten()
        .filter_map(|entry| {
            let path = entry.path();
            let name = path.file_name()?.to_str()?;
            if !is_laptop_battery_name(name) {
                return None;
            }
            (read_trimmed(path.join("type")).as_deref() == Some("Battery")).then_some(path)
        })
        .collect::<Vec<_>>();
    batteries.sort();
    batteries.into_iter().next()
}

fn health_percent(path: &Path) -> Option<f64> {
    let pairs = [
        ("energy_full", "energy_full_design"),
        ("charge_full", "charge_full_design"),
    ];
    for (full_name, design_name) in pairs {
        let (Some(full), Some(design)) = (
            read_u64(path.join(full_name)),
            read_u64(path.join(design_name)),
        ) else {
            continue;
        };
        if design > 0 {
            return Some((full as f64 / design as f64 * 100.0).clamp(0.0, 999.0));
        }
    }
    None
}

fn backlight_available() -> bool {
    fs::read_dir("/sys/class/backlight")
        .map(|mut entries| entries.next().is_some())
        .unwrap_or(false)
}

fn battery_state() -> Value {
    let Some(path) = first_battery() else {
        return Value::Null;
    };
    let name = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("battery");
    json!({
        "name": name,
        "capacity_percent": read_u64(path.join("capacity")),
        "status": read_trimmed(path.join("status")),
        "health_percent": health_percent(&path),
    })
}

fn ac_online() -> Option<bool> {
    let root = Path::new("/sys/class/power_supply");
    let entries = fs::read_dir(root).ok()?;
    let mut found = false;
    for entry in entries.flatten() {
        let path = entry.path();
        let supply_type = read_trimmed(path.join("type")).unwrap_or_default();
        if !matches!(supply_type.as_str(), "Mains" | "USB" | "USB_C") {
            continue;
        }
        found = true;
        if read_trimmed(path.join("online")).as_deref() == Some("1") {
            return Some(true);
        }
    }
    found.then_some(false)
}

fn command_exists(name: &str) -> bool {
    let Some(path) = env::var_os("PATH") else {
        return false;
    };
    env::split_paths(&path).any(|root| root.join(name).is_file())
}

fn command_output(name: &str, args: &[&str]) -> Option<String> {
    let output = ProcessCommand::new(name).args(args).output().ok()?;
    output
        .status
        .success()
        .then(|| String::from_utf8_lossy(&output.stdout).trim().to_owned())
}

fn first_governor() -> Option<String> {
    let root = Path::new("/sys/devices/system/cpu/cpufreq");
    for entry in fs::read_dir(root).ok()?.flatten() {
        let path = entry.path().join("scaling_governor");
        if let Some(value) = read_trimmed(path) {
            return Some(value);
        }
    }
    None
}

fn cpu_model() -> Option<String> {
    let content = fs::read_to_string("/proc/cpuinfo").ok()?;
    content.lines().find_map(|line| {
        let (key, value) = line.split_once(':')?;
        (key.trim() == "model name").then(|| value.trim().to_owned())
    })
}

fn local_diagnostics() -> Vec<Value> {
    let mut diagnostics = Vec::new();
    if !backlight_available() {
        diagnostics.push(json!({
            "severity": "warning",
            "code": "brightness-control-unavailable",
            "message": "No backlight device was detected.",
        }));
    }
    if fs::read_dir("/sys/class/leds")
        .map(|entries| {
            !entries.flatten().any(|entry| {
                entry
                    .file_name()
                    .to_string_lossy()
                    .to_ascii_lowercase()
                    .contains("kbd")
            })
        })
        .unwrap_or(true)
    {
        diagnostics.push(json!({
            "severity": "info",
            "code": "keyboard-backlight-unavailable",
            "message": "No keyboard backlight device was detected.",
        }));
    }
    if !command_exists("wpctl") {
        diagnostics.push(json!({
            "severity": "info",
            "code": "audio-control-unavailable",
            "message": "wpctl is not available in the user session.",
        }));
    }
    diagnostics
}

async fn system_proxy(connection: &zbus::Connection) -> Result<SystemProxy<'_>, String> {
    SystemProxy::new(connection)
        .await
        .map_err(|error| format!("system D-Bus unavailable: {error}"))
}

async fn agent_proxy(connection: &zbus::Connection) -> Result<AgentProxy<'_>, String> {
    AgentProxy::new(connection)
        .await
        .map_err(|error| format!("agent D-Bus unavailable: {error}"))
}

async fn status_value() -> Result<Value, String> {
    let system_bus = zbus::Connection::system()
        .await
        .map_err(|error| format!("system D-Bus unavailable: {error}"))?;
    let system = system_proxy(&system_bus).await?;

    let charge = parse_json_payload(
        &system
            .get_charge_state()
            .await
            .map_err(|error| format!("charge state failed: {error}"))?,
    );
    let thermal = parse_json_payload(
        &system
            .get_thermal_state()
            .await
            .map_err(|error| format!("thermal state failed: {error}"))?,
    );
    let cpu = parse_json_payload(
        &system
            .get_cpu_state()
            .await
            .map_err(|error| format!("CPU state failed: {error}"))?,
    );
    let telemetry = parse_json_payload(
        &system
            .get_telemetry_state()
            .await
            .map_err(|error| format!("telemetry state failed: {error}"))?,
    );

    let agent = match zbus::Connection::session().await {
        Ok(connection) => match agent_proxy(&connection).await {
            Ok(proxy) => match proxy.get_state().await {
                Ok(payload) => parse_json_payload(&payload),
                Err(_) => Value::Null,
            },
            Err(_) => Value::Null,
        },
        Err(_) => Value::Null,
    };

    let power_profile = command_output("powerprofilesctl", &["get"]);
    let kernel = read_trimmed("/proc/sys/kernel/osrelease");
    let battery = battery_state();
    let ac = ac_online();
    let diagnostics = local_diagnostics();

    Ok(json!({
        "machine": machine_name(),
        "os": os_name(),
        "kernel": kernel,
        "battery": battery,
        "ac_online": ac,
        "power_manager": {
            "provider": "power-profiles-daemon",
            "current_profile": power_profile,
        },
        "cpu_local": {
            "model_name": cpu_model(),
            "governor": first_governor(),
        },
        "capabilities": {
            "charge": charge,
            "thermal": thermal,
            "cpu": cpu,
            "telemetry": telemetry,
            "battery_saver": agent,
            "ac_monitoring": ac.is_some(),
            "audio_control": command_exists("wpctl"),
            "brightness_available": backlight_available(),
        },
        "diagnostics": diagnostics,
    }))
}

fn string_field<'a>(value: &'a Value, key: &str) -> Option<&'a str> {
    value.get(key)?.as_str()
}

fn integer_field(value: &Value, key: &str) -> Option<u64> {
    value.get(key)?.as_u64()
}

fn human_status(value: &Value) -> String {
    let mut lines = vec!["PowerDeck status".to_owned()];

    let machine = value.get("machine").unwrap_or(&Value::Null);
    let vendor = string_field(machine, "vendor").unwrap_or("Unknown vendor");
    let product = string_field(machine, "product").unwrap_or("Unknown machine");
    lines.push(format!("Machine: {vendor} {product}"));
    lines.push(format!(
        "OS: {}",
        value.get("os").and_then(Value::as_str).unwrap_or("Linux")
    ));
    lines.push(format!(
        "Kernel: {}",
        value
            .get("kernel")
            .and_then(Value::as_str)
            .unwrap_or("unknown")
    ));

    if let Some(battery) = value.get("battery").filter(|item| !item.is_null()) {
        let name = string_field(battery, "name").unwrap_or("Battery");
        let capacity = integer_field(battery, "capacity_percent")
            .map(|number| format!("{number}%"))
            .unwrap_or_else(|| "unknown".to_owned());
        let state = string_field(battery, "status").unwrap_or("unknown");
        let health = battery
            .get("health_percent")
            .and_then(Value::as_f64)
            .map(|number| format!("{number:.1}%"))
            .unwrap_or_else(|| "unknown".to_owned());
        lines.push(format!(
            "Battery {name}: {capacity}, {state}, health {health}"
        ));
    } else {
        lines.push("Battery: unavailable".to_owned());
    }

    let capabilities = value.get("capabilities").unwrap_or(&Value::Null);
    let charge = capabilities.get("charge").unwrap_or(&Value::Null);
    let charge_mode = string_field(charge, "current_mode").unwrap_or("unavailable");
    let interval = charge.get("interval").unwrap_or(&Value::Null);
    let interval_text = if interval.is_object() {
        let start = integer_field(interval, "start_percent")
            .map(|number| number.to_string())
            .unwrap_or_else(|| "?".to_owned());
        let end = integer_field(interval, "end_percent")
            .map(|number| number.to_string())
            .unwrap_or_else(|| "?".to_owned());
        format!(", interval {start}% -> {end}%")
    } else {
        String::new()
    };
    lines.push(format!("Charging: {charge_mode}{interval_text}"));

    let thermal = capabilities.get("thermal").unwrap_or(&Value::Null);
    lines.push(format!(
        "Thermal profile: {}",
        string_field(thermal, "current_profile").unwrap_or("unavailable")
    ));

    let cpu_local = value.get("cpu_local").unwrap_or(&Value::Null);
    let cpu = capabilities.get("cpu").unwrap_or(&Value::Null);
    let model = string_field(cpu_local, "model_name").unwrap_or("unknown CPU");
    let governor = string_field(cpu_local, "governor").unwrap_or("unknown");
    let maximum = integer_field(cpu, "max_performance_percent")
        .map(|number| format!("{number}%"))
        .unwrap_or_else(|| "unknown".to_owned());
    lines.push(format!(
        "CPU: {model}, governor {governor}, native max {maximum}"
    ));

    let ac = value
        .get("ac_online")
        .and_then(Value::as_bool)
        .map(|online| if online { "online" } else { "offline" })
        .unwrap_or("unknown");
    lines.push(format!("AC power: {ac}"));

    let manager = value
        .get("power_manager")
        .and_then(|item| item.get("current_profile"))
        .and_then(Value::as_str)
        .unwrap_or("unavailable");
    lines.push(format!("Power profile: {manager}"));

    let diagnostics = value
        .get("diagnostics")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let errors = diagnostics
        .iter()
        .filter(|item| string_field(item, "severity") == Some("error"))
        .count();
    let warnings = diagnostics
        .iter()
        .filter(|item| string_field(item, "severity") == Some("warning"))
        .count();
    let infos = diagnostics
        .iter()
        .filter(|item| string_field(item, "severity") == Some("info"))
        .count();
    lines.push(format!(
        "Diagnostics: {errors} error, {warnings} warning, {infos} info"
    ));
    for item in diagnostics {
        let severity = string_field(&item, "severity").unwrap_or("info");
        let code = string_field(&item, "code").unwrap_or("diagnostic");
        let message = string_field(&item, "message").unwrap_or("");
        lines.push(format!("  [{severity}] {code}: {message}"));
    }

    lines.join("\n")
}

async fn execute(command: CliCommand) -> Result<(), String> {
    if matches!(&command, CliCommand::Help) {
        print!("{}", usage());
        return Ok(());
    }

    if let CliCommand::Status { json: pretty } = &command {
        let value = status_value().await?;
        if *pretty {
            println!(
                "{}",
                serde_json::to_string_pretty(&value)
                    .map_err(|error| format!("JSON output failed: {error}"))?
            );
        } else {
            println!("{}", human_status(&value));
        }
        return Ok(());
    }

    let system_bus = zbus::Connection::system()
        .await
        .map_err(|error| format!("system D-Bus unavailable: {error}"))?;
    let system = system_proxy(&system_bus).await?;

    match command {
        CliCommand::Ping => {
            let system_reply = system
                .ping()
                .await
                .map_err(|error| format!("system ping failed: {error}"))?;
            let agent_reply = match zbus::Connection::session().await {
                Ok(connection) => match agent_proxy(&connection).await {
                    Ok(proxy) => proxy
                        .ping()
                        .await
                        .unwrap_or_else(|_| "unavailable".to_owned()),
                    Err(_) => "unavailable".to_owned(),
                },
                Err(_) => "unavailable".to_owned(),
            };
            println!("system: {system_reply}");
            println!("agent: {agent_reply}");
        }
        CliCommand::Telemetry { json } => {
            let payload = system
                .get_telemetry_state()
                .await
                .map_err(|error| format!("telemetry failed: {error}"))?;
            print_payload(&payload, json);
        }
        CliCommand::ChargeGet { json } => {
            let payload = system
                .get_charge_state()
                .await
                .map_err(|error| format!("charge state failed: {error}"))?;
            print_payload(&payload, json);
        }
        CliCommand::ChargeMode { mode } => {
            let payload = system
                .set_charge_mode(&mode)
                .await
                .map_err(|error| format!("charge mode failed: {error}"))?;
            print_payload(&payload, true);
        }
        CliCommand::ChargeThresholds { start, end } => {
            let payload = system
                .set_charge_thresholds(start, end)
                .await
                .map_err(|error| format!("charge thresholds failed: {error}"))?;
            print_payload(&payload, true);
        }
        CliCommand::ThermalGet { json } => {
            let payload = system
                .get_thermal_state()
                .await
                .map_err(|error| format!("thermal state failed: {error}"))?;
            print_payload(&payload, json);
        }
        CliCommand::ThermalSet { profile } => {
            let payload = system
                .set_thermal_profile(&profile)
                .await
                .map_err(|error| format!("thermal profile failed: {error}"))?;
            print_payload(&payload, true);
        }
        CliCommand::CpuGet { json } => {
            let payload = system
                .get_cpu_state()
                .await
                .map_err(|error| format!("CPU state failed: {error}"))?;
            print_payload(&payload, json);
        }
        CliCommand::CpuSet {
            disable_turbo,
            max_performance_percent,
        } => {
            let payload = system
                .set_cpu_policy(disable_turbo, max_performance_percent)
                .await
                .map_err(|error| format!("CPU policy failed: {error}"))?;
            print_payload(&payload, true);
        }
        CliCommand::SaverState { json } => {
            let connection = zbus::Connection::session()
                .await
                .map_err(|error| format!("session D-Bus unavailable: {error}"))?;
            let agent = agent_proxy(&connection).await?;
            let payload = agent
                .get_state()
                .await
                .map_err(|error| format!("Battery Saver state failed: {error}"))?;
            print_payload(&payload, json);
        }
        CliCommand::SaverSettings { json } => {
            let connection = zbus::Connection::session()
                .await
                .map_err(|error| format!("session D-Bus unavailable: {error}"))?;
            let agent = agent_proxy(&connection).await?;
            let payload = agent
                .get_settings()
                .await
                .map_err(|error| format!("Battery Saver settings failed: {error}"))?;
            print_payload(&payload, json);
        }
        CliCommand::SaverEnabled { enabled } => {
            let connection = zbus::Connection::session()
                .await
                .map_err(|error| format!("session D-Bus unavailable: {error}"))?;
            let agent = agent_proxy(&connection).await?;
            let payload = agent
                .set_saver_enabled(enabled)
                .await
                .map_err(|error| format!("Battery Saver update failed: {error}"))?;
            print_payload(&payload, true);
        }
        CliCommand::SaverSetSettings { payload } => {
            let connection = zbus::Connection::session()
                .await
                .map_err(|error| format!("session D-Bus unavailable: {error}"))?;
            let agent = agent_proxy(&connection).await?;
            let result = agent
                .set_settings(&payload)
                .await
                .map_err(|error| format!("Battery Saver settings update failed: {error}"))?;
            print_payload(&result, true);
        }
        CliCommand::Status { .. } | CliCommand::Help => unreachable!(),
    }
    Ok(())
}

#[tokio::main(flavor = "current_thread")]
async fn main() {
    let mut argv = env::args();
    let program = argv.next().unwrap_or_else(|| "powerdeckctl".to_owned());
    let program_name = Path::new(&program)
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("powerdeckctl");
    let args: Vec<String> = argv.collect();

    let command = match parse_compat(program_name, &args) {
        Ok(command) => command,
        Err(error) => {
            eprintln!("powerdeckctl: {error}\n\n{}", usage());
            std::process::exit(2);
        }
    };

    if let Err(error) = execute(command).await {
        eprintln!("powerdeckctl: {error}");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_status_json() {
        assert_eq!(
            parse_canonical(&["status".to_owned(), "--json".to_owned()]).unwrap(),
            CliCommand::Status { json: true }
        );
    }

    #[test]
    fn parses_cpu_policy() {
        assert_eq!(
            parse_canonical(&[
                "cpu".to_owned(),
                "set".to_owned(),
                "turbo-off".to_owned(),
                "60".to_owned(),
            ])
            .unwrap(),
            CliCommand::CpuSet {
                disable_turbo: true,
                max_performance_percent: 60,
            }
        );
    }

    #[test]
    fn rejects_invalid_threshold_order() {
        let error = parse_canonical(&[
            "charge".to_owned(),
            "thresholds".to_owned(),
            "80".to_owned(),
            "70".to_owned(),
        ])
        .unwrap_err();
        assert!(error.contains("below"));
    }

    #[test]
    fn compatibility_thermalctl_maps_set() {
        assert_eq!(
            parse_compat(
                "powerdeck-thermalctl",
                &["set".to_owned(), "quiet".to_owned()]
            )
            .unwrap(),
            CliCommand::ThermalSet {
                profile: "quiet".to_owned()
            }
        );
    }

    #[test]
    fn human_status_keeps_core_fields() {
        let value = json!({
            "machine": {"vendor": "Dell Inc.", "product": "Test"},
            "os": "CachyOS",
            "kernel": "test-kernel",
            "battery": {
                "name": "BAT0",
                "capacity_percent": 55,
                "status": "Charging",
                "health_percent": 99.5,
            },
            "ac_online": true,
            "power_manager": {"current_profile": "balanced"},
            "cpu_local": {"model_name": "Test CPU", "governor": "powersave"},
            "capabilities": {
                "charge": {"current_mode": "custom", "interval": null},
                "thermal": {"current_profile": "balanced"},
                "cpu": {"max_performance_percent": 100},
            },
            "diagnostics": [],
        });
        let text = human_status(&value);
        assert!(text.contains("Dell Inc. Test"));
        assert!(text.contains("Battery BAT0: 55%"));
        assert!(text.contains("Thermal profile: balanced"));
    }

    #[test]
    fn ignores_peripheral_power_supply_batteries() {
        assert!(is_laptop_battery_name("BAT0"));
        assert!(is_laptop_battery_name("BAT1"));
        assert!(!is_laptop_battery_name("hidpp_battery_0"));
        assert!(!is_laptop_battery_name("mouse_battery"));
    }

    #[test]
    fn dbus_contract_constants_match_runtime() {
        assert_eq!(SYSTEM_SERVICE, "org.powerdeck.System1");
        assert_eq!(SYSTEM_PATH, "/org/powerdeck/System1");
        assert_eq!(SYSTEM_INTERFACE, "org.powerdeck.System1");
        assert_eq!(AGENT_SERVICE, "org.powerdeck.Agent1");
        assert_eq!(AGENT_PATH, "/org/powerdeck/Agent1");
        assert_eq!(AGENT_INTERFACE, "org.powerdeck.Agent1");
    }
}
