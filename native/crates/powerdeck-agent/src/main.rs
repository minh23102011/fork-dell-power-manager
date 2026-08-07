use std::collections::BTreeMap;
use std::fs;
use std::future::pending;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::Arc;

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use tokio::process::Command;
use tokio::sync::Mutex;
use tokio::time::{Duration, sleep, timeout};
use zbus::{interface, proxy};

const BUS_NAME: &str = "org.powerdeck.Agent1";
const OBJECT_PATH: &str = "/org/powerdeck/Agent1";
const COMMAND_TIMEOUT: Duration = Duration::from_secs(8);

#[proxy(
    interface = "org.powerdeck.System1",
    default_service = "org.powerdeck.System1",
    default_path = "/org/powerdeck/System1"
)]
trait System {
    #[zbus(name = "GetThermalState")]
    async fn get_thermal_state(&self) -> zbus::Result<String>;

    #[zbus(name = "SetThermalProfile")]
    async fn set_thermal_profile(&self, profile: &str) -> zbus::Result<String>;

    #[zbus(name = "GetCpuState")]
    async fn get_cpu_state(&self) -> zbus::Result<String>;

    #[zbus(name = "SetCpuPolicy")]
    async fn set_cpu_policy(
        &self,
        disable_turbo: bool,
        max_performance_percent: i32,
    ) -> zbus::Result<String>;
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
struct SaverSettings {
    enabled: bool,
    auto_enable_on_battery: bool,
    restore_on_ac: bool,
    brightness_cap_percent: u8,
    only_lower_brightness: bool,
    target_refresh_rate_hz: f64,
    power_profile: String,
    thermal_profile: String,
    disable_turbo: bool,
    max_performance_percent: u8,
    keyboard_backlight_level: u8,
    mute_audio: bool,
}

impl Default for SaverSettings {
    fn default() -> Self {
        Self {
            enabled: true,
            auto_enable_on_battery: true,
            restore_on_ac: true,
            brightness_cap_percent: 40,
            only_lower_brightness: true,
            target_refresh_rate_hz: 60.0,
            power_profile: "power-saver".to_owned(),
            thermal_profile: "quiet".to_owned(),
            disable_turbo: true,
            max_performance_percent: 60,
            keyboard_backlight_level: 0,
            mute_audio: false,
        }
    }
}

impl SaverSettings {
    fn validate(&self) -> Result<(), String> {
        if !(1..=100).contains(&self.brightness_cap_percent) {
            return Err("brightness_cap_percent must be between 1 and 100".to_owned());
        }
        if !(1..=100).contains(&self.max_performance_percent) {
            return Err("max_performance_percent must be between 1 and 100".to_owned());
        }
        if self.keyboard_backlight_level > 100 {
            return Err("keyboard_backlight_level must be between 0 and 100".to_owned());
        }
        if !(1.0..=1000.0).contains(&self.target_refresh_rate_hz)
            || !self.target_refresh_rate_hz.is_finite()
        {
            return Err("target_refresh_rate_hz must be between 1 and 1000".to_owned());
        }
        if !matches!(
            self.thermal_profile.as_str(),
            "quiet" | "cool" | "balanced" | "performance"
        ) {
            return Err("thermal_profile is invalid".to_owned());
        }
        if !matches!(
            self.power_profile.as_str(),
            "power-saver" | "balanced" | "performance"
        ) {
            return Err("power_profile is invalid".to_owned());
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Default)]
struct Ledger {
    brightness: Option<OwnedBacklight>,
    display: Option<OwnedDisplay>,
    power_profile: Option<OwnedValue<String>>,
    thermal_profile: Option<OwnedValue<String>>,
    cpu_policy: Option<OwnedCpuPolicy>,
    keyboard_backlight: Option<OwnedBacklight>,
    audio_muted: Option<OwnedValue<bool>>,
}

#[derive(Debug, Clone)]
struct OwnedValue<T> {
    previous: T,
    applied: T,
}

#[derive(Debug, Clone)]
struct OwnedBacklight {
    device: String,
    previous: u64,
    applied: u64,
}

#[derive(Debug, Clone)]
struct OwnedDisplay {
    connector: String,
    previous_mode: String,
    applied_mode: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct CpuPolicy {
    disable_turbo: bool,
    max_performance_percent: u8,
}

#[derive(Debug, Clone)]
struct OwnedCpuPolicy {
    previous: CpuPolicy,
    applied: CpuPolicy,
}

#[derive(Debug)]
struct AgentState {
    settings: SaverSettings,
    active: bool,
    activation: Option<String>,
    ledger: Ledger,
    last_on_ac: Option<bool>,
    last_error: Option<String>,
}

#[derive(Clone)]
struct AgentService {
    state: Arc<Mutex<AgentState>>,
    system_bus: zbus::Connection,
}

impl AgentService {
    async fn set_enabled(&self, enabled: bool, activation: &str) -> Result<(), String> {
        let mut state = self.state.lock().await;
        if state.active == enabled {
            if enabled && activation == "manual" {
                state.activation = Some("manual".to_owned());
                persist_runtime_state(&state)?;
            }
            return Ok(());
        }

        if enabled {
            let settings = state.settings.clone();
            let mut ledger = Ledger::default();
            state.activation = Some(activation.to_owned());
            state.last_error = None;
            persist_snapshot(
                false,
                state.activation.as_deref(),
                state.last_on_ac,
                &ledger,
                None,
            )?;

            match activate(
                &self.system_bus,
                &settings,
                state.activation.as_deref(),
                state.last_on_ac,
                &mut ledger,
            )
            .await
            {
                Ok(()) => {
                    state.ledger = ledger;
                    state.active = true;
                    state.last_error = None;
                    persist_runtime_state(&state)?;
                    Ok(())
                }
                Err(error) => {
                    let rollback = restore(&self.system_bus, &ledger).await;
                    if let Err(rollback_error) = rollback {
                        let combined = format!(
                            "activation failed: {error}; rollback failed: {rollback_error}"
                        );
                        state.ledger = ledger;
                        state.active = true;
                        state.last_error = Some(combined.clone());
                        persist_runtime_state(&state)?;
                        return Err(combined);
                    }
                    state.ledger = Ledger::default();
                    state.active = false;
                    state.activation = None;
                    state.last_error = Some(error.clone());
                    persist_runtime_state(&state)?;
                    Err(error)
                }
            }
        } else {
            match restore(&self.system_bus, &state.ledger).await {
                Ok(()) => {
                    state.ledger = Ledger::default();
                    state.active = false;
                    state.activation = None;
                    state.last_error = None;
                    persist_runtime_state(&state)?;
                    Ok(())
                }
                Err(error) => {
                    state.last_error = Some(error.clone());
                    persist_runtime_state(&state)?;
                    Err(error)
                }
            }
        }
    }
}

#[interface(name = "org.powerdeck.Agent1")]
impl AgentService {
    #[zbus(name = "Ping")]
    fn ping(&self) -> &str {
        "pong"
    }

    #[zbus(name = "GetState")]
    async fn get_state(&self) -> String {
        let state = self.state.lock().await;
        state_json(&state).to_string()
    }

    #[zbus(name = "GetSettings")]
    async fn get_settings(&self) -> String {
        let state = self.state.lock().await;
        serde_json::to_string(&state.settings).unwrap_or_else(|_| "{}".to_owned())
    }

    #[zbus(name = "SetSaverEnabled")]
    async fn set_saver_enabled(&self, enabled: bool) -> Result<String, zbus::fdo::Error> {
        self.set_enabled(enabled, "manual")
            .await
            .map_err(zbus::fdo::Error::Failed)?;
        Ok(self.get_state().await)
    }

    #[zbus(name = "SetSettings")]
    async fn set_settings(&self, settings_json: &str) -> Result<String, zbus::fdo::Error> {
        let settings: SaverSettings = serde_json::from_str(settings_json)
            .map_err(|error| zbus::fdo::Error::InvalidArgs(error.to_string()))?;
        settings.validate().map_err(zbus::fdo::Error::InvalidArgs)?;

        {
            let mut state = self.state.lock().await;
            if state.active {
                return Err(zbus::fdo::Error::Failed(
                    "Disable Battery Saver before changing settings.".to_owned(),
                ));
            }
            state.settings = settings.clone();
            persist_runtime_state(&state)
                .map_err(|error| zbus::fdo::Error::Failed(error.to_string()))?;
        }
        save_settings(&settings).map_err(|error| zbus::fdo::Error::Failed(error.to_string()))?;
        serde_json::to_string(&settings)
            .map_err(|error| zbus::fdo::Error::Failed(error.to_string()))
    }
}

fn state_json(state: &AgentState) -> Value {
    let on_ac_power = ac_online();
    json!({
        "enabled": state.active,
        "active": state.active,
        "activation": state.activation,
        "automatic_session": state.activation.as_deref() == Some("automatic"),
        "last_error": state.last_error,
        "on_ac_power": on_ac_power,
        "ac_online": on_ac_power,
        "settings": state.settings,
    })
}

async fn activate(
    system_bus: &zbus::Connection,
    settings: &SaverSettings,
    activation: Option<&str>,
    last_on_ac: Option<bool>,
    ledger: &mut Ledger,
) -> Result<(), String> {
    settings.validate()?;

    apply_brightness(settings, ledger).await?;
    persist_snapshot(true, activation, last_on_ac, ledger, None)?;

    apply_display(settings, ledger).await?;
    persist_snapshot(true, activation, last_on_ac, ledger, None)?;

    apply_power_profile(settings, ledger).await?;
    persist_snapshot(true, activation, last_on_ac, ledger, None)?;

    apply_thermal(system_bus, settings, ledger).await?;
    persist_snapshot(true, activation, last_on_ac, ledger, None)?;

    apply_cpu(system_bus, settings, ledger).await?;
    persist_snapshot(true, activation, last_on_ac, ledger, None)?;

    apply_keyboard(settings, ledger).await?;
    persist_snapshot(true, activation, last_on_ac, ledger, None)?;

    apply_audio(settings, ledger).await?;
    persist_snapshot(true, activation, last_on_ac, ledger, None)?;
    Ok(())
}

async fn apply_brightness(settings: &SaverSettings, ledger: &mut Ledger) -> Result<(), String> {
    let Some(device) = first_backlight(Path::new("/sys/class/backlight"), |_| true) else {
        return Ok(());
    };
    let current = read_u64(&device.path.join("brightness")).ok_or("brightness read failed")?;
    let maximum =
        read_u64(&device.path.join("max_brightness")).ok_or("brightness maximum read failed")?;
    if maximum == 0 {
        return Ok(());
    }
    let target =
        ((maximum * u64::from(settings.brightness_cap_percent) + 50) / 100).clamp(1, maximum);
    if settings.only_lower_brightness && current <= target {
        return Ok(());
    }
    if current == target {
        return Ok(());
    }

    run_command(
        "brightnessctl",
        &["-d", &device.name, "set", &target.to_string()],
    )
    .await?;
    let observed =
        read_u64(&device.path.join("brightness")).ok_or("brightness verification failed")?;
    if observed != target {
        return Err(format!(
            "brightness verification failed: requested {target}, observed {observed}"
        ));
    }
    ledger.brightness = Some(OwnedBacklight {
        device: device.name,
        previous: current,
        applied: observed,
    });
    Ok(())
}

async fn apply_display(settings: &SaverSettings, ledger: &mut Ledger) -> Result<(), String> {
    if !command_exists("niri") {
        return Ok(());
    }
    let Some(selection) = display_selection(settings.target_refresh_rate_hz).await? else {
        return Ok(());
    };
    if selection.previous_mode == selection.target_mode {
        return Ok(());
    }

    run_command(
        "niri",
        &[
            "msg",
            "output",
            &selection.connector,
            "mode",
            &selection.target_mode,
        ],
    )
    .await?;
    let observed = current_display_mode(&selection.connector).await?;
    if observed.as_deref() != Some(selection.target_mode.as_str()) {
        return Err(format!(
            "display verification failed: requested {}, observed {}",
            selection.target_mode,
            observed.unwrap_or_else(|| "unavailable".to_owned())
        ));
    }
    ledger.display = Some(OwnedDisplay {
        connector: selection.connector,
        previous_mode: selection.previous_mode,
        applied_mode: selection.target_mode,
    });
    Ok(())
}

async fn apply_power_profile(settings: &SaverSettings, ledger: &mut Ledger) -> Result<(), String> {
    if !command_exists("powerprofilesctl") {
        return Ok(());
    }
    let previous = command_stdout("powerprofilesctl", &["get"]).await?;
    let previous = previous.trim().to_owned();
    if previous == settings.power_profile {
        return Ok(());
    }
    run_command("powerprofilesctl", &["set", &settings.power_profile]).await?;
    let applied = command_stdout("powerprofilesctl", &["get"]).await?;
    let applied = applied.trim().to_owned();
    if applied != settings.power_profile {
        return Err("power profile verification failed".to_owned());
    }
    ledger.power_profile = Some(OwnedValue { previous, applied });
    Ok(())
}

async fn apply_thermal(
    system_bus: &zbus::Connection,
    settings: &SaverSettings,
    ledger: &mut Ledger,
) -> Result<(), String> {
    let proxy = system_proxy(system_bus).await?;
    let before_payload = proxy
        .get_thermal_state()
        .await
        .map_err(|error| format!("thermal state read failed: {error}"))?;
    let Some(previous) = json_string_field(&before_payload, "current_profile") else {
        return Ok(());
    };
    if previous == settings.thermal_profile {
        return Ok(());
    }
    let result = proxy
        .set_thermal_profile(&settings.thermal_profile)
        .await
        .map_err(|error| format!("thermal apply failed: {error}"))?;
    let applied = json_string_field(&result, "current_profile")
        .ok_or("thermal verification result is malformed")?;
    if applied != settings.thermal_profile {
        return Err("thermal profile verification failed".to_owned());
    }
    ledger.thermal_profile = Some(OwnedValue { previous, applied });
    Ok(())
}

async fn apply_cpu(
    system_bus: &zbus::Connection,
    settings: &SaverSettings,
    ledger: &mut Ledger,
) -> Result<(), String> {
    let proxy = system_proxy(system_bus).await?;
    let before_payload = proxy
        .get_cpu_state()
        .await
        .map_err(|error| format!("CPU policy state read failed: {error}"))?;
    let Some(previous) = cpu_policy_from_json(&before_payload) else {
        return Ok(());
    };
    let requested = CpuPolicy {
        disable_turbo: settings.disable_turbo,
        max_performance_percent: settings.max_performance_percent,
    };
    if previous == requested {
        return Ok(());
    }
    let result = proxy
        .set_cpu_policy(
            requested.disable_turbo,
            i32::from(requested.max_performance_percent),
        )
        .await
        .map_err(|error| format!("CPU policy apply failed: {error}"))?;
    let applied = CpuPolicy {
        disable_turbo: json_bool_field(&result, "current_disable_turbo")
            .ok_or("CPU policy verification result is malformed")?,
        max_performance_percent: json_u8_field(&result, "current_max_performance_percent")
            .ok_or("CPU policy verification result is malformed")?,
    };
    if applied != requested {
        return Err("CPU policy verification failed".to_owned());
    }
    ledger.cpu_policy = Some(OwnedCpuPolicy { previous, applied });
    Ok(())
}

async fn apply_keyboard(settings: &SaverSettings, ledger: &mut Ledger) -> Result<(), String> {
    let Some(device) = first_backlight(Path::new("/sys/class/leds"), |name| {
        name.to_ascii_lowercase().contains("kbd")
    }) else {
        return Ok(());
    };
    let previous =
        read_u64(&device.path.join("brightness")).ok_or("keyboard backlight read failed")?;
    let target = u64::from(settings.keyboard_backlight_level);
    if previous == target {
        return Ok(());
    }
    run_command(
        "brightnessctl",
        &["-d", &device.name, "set", &target.to_string()],
    )
    .await?;
    let applied = read_u64(&device.path.join("brightness"))
        .ok_or("keyboard backlight verification failed")?;
    if applied != target {
        return Err(format!(
            "keyboard backlight verification failed: requested {target}, observed {applied}"
        ));
    }
    ledger.keyboard_backlight = Some(OwnedBacklight {
        device: device.name,
        previous,
        applied,
    });
    Ok(())
}

async fn apply_audio(settings: &SaverSettings, ledger: &mut Ledger) -> Result<(), String> {
    if !settings.mute_audio || !command_exists("wpctl") {
        return Ok(());
    }
    let Some(previous) = audio_muted().await? else {
        return Ok(());
    };
    if previous {
        return Ok(());
    }
    run_command("wpctl", &["set-mute", "@DEFAULT_AUDIO_SINK@", "1"]).await?;
    let applied = audio_muted().await?.ok_or("audio mute read-back failed")?;
    if !applied {
        return Err("audio mute verification failed".to_owned());
    }
    ledger.audio_muted = Some(OwnedValue { previous, applied });
    Ok(())
}

async fn restore(system_bus: &zbus::Connection, ledger: &Ledger) -> Result<(), String> {
    let mut failures = Vec::new();

    restore_audio(ledger, &mut failures).await;
    restore_keyboard(ledger, &mut failures).await;
    restore_cpu(system_bus, ledger, &mut failures).await;
    restore_thermal(system_bus, ledger, &mut failures).await;
    restore_power_profile(ledger, &mut failures).await;
    restore_display(ledger, &mut failures).await;
    restore_brightness(ledger, &mut failures).await;

    if failures.is_empty() {
        Ok(())
    } else {
        Err(format!("restore failures: {}", failures.join("; ")))
    }
}

async fn restore_audio(ledger: &Ledger, failures: &mut Vec<String>) {
    let Some(owned) = &ledger.audio_muted else {
        return;
    };
    match audio_muted().await {
        Ok(Some(current)) if current == owned.applied => {
            let value = if owned.previous { "1" } else { "0" };
            if let Err(error) =
                run_command("wpctl", &["set-mute", "@DEFAULT_AUDIO_SINK@", value]).await
            {
                failures.push(format!("audio: {error}"));
                return;
            }
            match audio_muted().await {
                Ok(Some(observed)) if observed == owned.previous => {}
                Ok(_) => failures.push("audio: restore verification failed".to_owned()),
                Err(error) => failures.push(format!("audio: {error}")),
            }
        }
        Ok(_) => {}
        Err(error) => failures.push(format!("audio: {error}")),
    }
}

async fn restore_keyboard(ledger: &Ledger, failures: &mut Vec<String>) {
    let Some(owned) = &ledger.keyboard_backlight else {
        return;
    };
    let path = Path::new("/sys/class/leds")
        .join(&owned.device)
        .join("brightness");
    if read_u64(&path) != Some(owned.applied) {
        return;
    }
    if let Err(error) = run_command(
        "brightnessctl",
        &["-d", &owned.device, "set", &owned.previous.to_string()],
    )
    .await
    {
        failures.push(format!("keyboard: {error}"));
        return;
    }
    if read_u64(&path) != Some(owned.previous) {
        failures.push("keyboard: restore verification failed".to_owned());
    }
}

async fn restore_cpu(system_bus: &zbus::Connection, ledger: &Ledger, failures: &mut Vec<String>) {
    let Some(owned) = &ledger.cpu_policy else {
        return;
    };
    let proxy = match system_proxy(system_bus).await {
        Ok(proxy) => proxy,
        Err(error) => {
            failures.push(format!("cpu: {error}"));
            return;
        }
    };
    let current = match proxy.get_cpu_state().await {
        Ok(payload) => cpu_policy_from_json(&payload),
        Err(error) => {
            failures.push(format!("cpu: state read failed: {error}"));
            return;
        }
    };
    if current.as_ref() != Some(&owned.applied) {
        return;
    }
    if let Err(error) = proxy
        .set_cpu_policy(
            owned.previous.disable_turbo,
            i32::from(owned.previous.max_performance_percent),
        )
        .await
    {
        failures.push(format!("cpu: {error}"));
    }
}

async fn restore_thermal(
    system_bus: &zbus::Connection,
    ledger: &Ledger,
    failures: &mut Vec<String>,
) {
    let Some(owned) = &ledger.thermal_profile else {
        return;
    };
    let proxy = match system_proxy(system_bus).await {
        Ok(proxy) => proxy,
        Err(error) => {
            failures.push(format!("thermal: {error}"));
            return;
        }
    };
    let current = match proxy.get_thermal_state().await {
        Ok(payload) => json_string_field(&payload, "current_profile"),
        Err(error) => {
            failures.push(format!("thermal: state read failed: {error}"));
            return;
        }
    };
    if current.as_deref() != Some(owned.applied.as_str()) {
        return;
    }
    if let Err(error) = proxy.set_thermal_profile(&owned.previous).await {
        failures.push(format!("thermal: {error}"));
    }
}

async fn restore_power_profile(ledger: &Ledger, failures: &mut Vec<String>) {
    let Some(owned) = &ledger.power_profile else {
        return;
    };
    if !command_exists("powerprofilesctl") {
        return;
    }
    match command_stdout("powerprofilesctl", &["get"]).await {
        Ok(current) if current.trim() == owned.applied => {
            if let Err(error) = run_command("powerprofilesctl", &["set", &owned.previous]).await {
                failures.push(format!("power profile: {error}"));
                return;
            }
            match command_stdout("powerprofilesctl", &["get"]).await {
                Ok(observed) if observed.trim() == owned.previous => {}
                Ok(_) => failures.push("power profile: restore verification failed".to_owned()),
                Err(error) => failures.push(format!("power profile: {error}")),
            }
        }
        Ok(_) => {}
        Err(error) => failures.push(format!("power profile: {error}")),
    }
}

async fn restore_display(ledger: &Ledger, failures: &mut Vec<String>) {
    let Some(owned) = &ledger.display else {
        return;
    };
    let current = match current_display_mode(&owned.connector).await {
        Ok(value) => value,
        Err(error) => {
            failures.push(format!("display: {error}"));
            return;
        }
    };
    if current.as_deref() != Some(owned.applied_mode.as_str()) {
        return;
    }
    if let Err(error) = run_command(
        "niri",
        &[
            "msg",
            "output",
            &owned.connector,
            "mode",
            &owned.previous_mode,
        ],
    )
    .await
    {
        failures.push(format!("display: {error}"));
        return;
    }
    match current_display_mode(&owned.connector).await {
        Ok(Some(observed)) if observed == owned.previous_mode => {}
        Ok(_) => failures.push("display: restore verification failed".to_owned()),
        Err(error) => failures.push(format!("display: {error}")),
    }
}

async fn restore_brightness(ledger: &Ledger, failures: &mut Vec<String>) {
    let Some(owned) = &ledger.brightness else {
        return;
    };
    let path = Path::new("/sys/class/backlight")
        .join(&owned.device)
        .join("brightness");
    if read_u64(&path) != Some(owned.applied) {
        return;
    }
    if let Err(error) = run_command(
        "brightnessctl",
        &["-d", &owned.device, "set", &owned.previous.to_string()],
    )
    .await
    {
        failures.push(format!("brightness: {error}"));
        return;
    }
    if read_u64(&path) != Some(owned.previous) {
        failures.push("brightness: restore verification failed".to_owned());
    }
}

async fn system_proxy(connection: &zbus::Connection) -> Result<SystemProxy<'_>, String> {
    SystemProxy::new(connection)
        .await
        .map_err(|error| format!("system D-Bus unavailable: {error}"))
}

async fn ac_monitor(service: AgentService) {
    let mut previous = ac_online();
    {
        let mut state = service.state.lock().await;
        state.last_on_ac = previous;
        let _ = persist_runtime_state(&state);
    }

    loop {
        sleep(Duration::from_secs(2)).await;
        let current = ac_online();
        if current == previous {
            continue;
        }
        previous = current;

        let (settings, active, automatic) = {
            let mut state = service.state.lock().await;
            state.last_on_ac = current;
            let _ = persist_runtime_state(&state);
            (
                state.settings.clone(),
                state.active,
                state.activation.as_deref() == Some("automatic"),
            )
        };

        if current == Some(false) && settings.enabled && settings.auto_enable_on_battery && !active
        {
            let _ = service.set_enabled(true, "automatic").await;
        } else if current == Some(true) && settings.restore_on_ac && active && automatic {
            let _ = service.set_enabled(false, "automatic").await;
        }
    }
}

#[derive(Debug)]
struct BacklightDevice {
    name: String,
    path: PathBuf,
}

fn first_backlight(root: &Path, predicate: impl Fn(&str) -> bool) -> Option<BacklightDevice> {
    let mut devices: Vec<PathBuf> = fs::read_dir(root)
        .ok()?
        .flatten()
        .map(|entry| entry.path())
        .filter(|path| path.is_dir())
        .collect();
    devices.sort();
    for path in devices {
        let name = path.file_name()?.to_string_lossy().to_string();
        if predicate(&name) {
            return Some(BacklightDevice { name, path });
        }
    }
    None
}

#[derive(Debug, Clone)]
struct DisplayMode {
    width: i64,
    height: i64,
    refresh_hz: f64,
    current: bool,
    preferred: bool,
}

impl DisplayMode {
    fn label(&self) -> String {
        format!("{}x{}@{:.3}", self.width, self.height, self.refresh_hz)
    }
}

#[derive(Debug)]
struct DisplaySelection {
    connector: String,
    previous_mode: String,
    target_mode: String,
}

async fn display_selection(target_hz: f64) -> Result<Option<DisplaySelection>, String> {
    let payload = niri_outputs().await?;
    let Some((connector, output)) = select_internal_output(&payload) else {
        return Ok(None);
    };
    let modes = parse_modes(output);
    let Some((reference, target)) = select_battery_mode(&modes, target_hz) else {
        return Ok(None);
    };
    Ok(Some(DisplaySelection {
        connector,
        previous_mode: reference.label(),
        target_mode: target.label(),
    }))
}

fn select_battery_mode(
    modes: &[DisplayMode],
    target_hz: f64,
) -> Option<(&DisplayMode, &DisplayMode)> {
    let reference = modes
        .iter()
        .find(|mode| mode.current)
        .or_else(|| modes.iter().find(|mode| mode.preferred))?;
    let target = modes
        .iter()
        .filter(|mode| {
            mode.width == reference.width
                && mode.height == reference.height
                && (mode.refresh_hz - target_hz).abs() <= 1.0
        })
        .min_by(|left, right| {
            (left.refresh_hz - target_hz)
                .abs()
                .total_cmp(&(right.refresh_hz - target_hz).abs())
        })?;
    Some((reference, target))
}

async fn current_display_mode(connector: &str) -> Result<Option<String>, String> {
    let payload = niri_outputs().await?;
    let Some(output) = output_map(&payload)
        .and_then(|outputs| outputs.get(connector))
        .and_then(Value::as_object)
    else {
        return Ok(None);
    };
    Ok(parse_modes(output)
        .into_iter()
        .find(|mode| mode.current)
        .map(|mode| mode.label()))
}

async fn niri_outputs() -> Result<Value, String> {
    let text = command_stdout("niri", &["msg", "--json", "outputs"]).await?;
    serde_json::from_str(&text).map_err(|error| format!("niri output JSON is malformed: {error}"))
}

fn output_map(payload: &Value) -> Option<&Map<String, Value>> {
    if let Some(root) = payload.as_object() {
        if let Some(ok) = root.get("Ok").and_then(Value::as_object) {
            if let Some(outputs) = ok
                .get("Outputs")
                .or_else(|| ok.get("outputs"))
                .and_then(Value::as_object)
            {
                return Some(outputs);
            }
            return Some(ok);
        }
        if let Some(outputs) = root
            .get("Outputs")
            .or_else(|| root.get("outputs"))
            .and_then(Value::as_object)
        {
            return Some(outputs);
        }
        return Some(root);
    }
    None
}

fn select_internal_output(payload: &Value) -> Option<(String, &Map<String, Value>)> {
    output_map(payload)?.iter().find_map(|(connector, value)| {
        let output = value.as_object()?;
        let lower = connector.to_ascii_lowercase();
        let internal =
            lower.starts_with("edp") || lower.starts_with("lvds") || lower.starts_with("dsi");
        let enabled = output.get("logical").and_then(Value::as_object).is_some()
            || output
                .get("current_mode")
                .is_some_and(|value| !value.is_null());
        (internal && enabled).then_some((connector.clone(), output))
    })
}

fn parse_modes(output: &Map<String, Value>) -> Vec<DisplayMode> {
    let Some(values) = output.get("modes").and_then(Value::as_array) else {
        return Vec::new();
    };
    let current_index = output.get("current_mode").and_then(Value::as_i64);
    let current_mapping = output.get("current_mode").and_then(Value::as_object);
    values
        .iter()
        .enumerate()
        .filter_map(|(index, value)| {
            let mode = value.as_object()?;
            let width = mode.get("width")?.as_i64()?;
            let height = mode.get("height")?.as_i64()?;
            let refresh_hz = refresh_hz(mode)?;
            let current = i64::try_from(index).ok() == current_index
                || current_mapping.is_some_and(|current| same_mode(mode, current));
            let preferred = mode
                .get("is_preferred")
                .or_else(|| mode.get("preferred"))
                .and_then(Value::as_bool)
                .unwrap_or(false);
            Some(DisplayMode {
                width,
                height,
                refresh_hz,
                current,
                preferred,
            })
        })
        .collect()
}

fn same_mode(left: &Map<String, Value>, right: &Map<String, Value>) -> bool {
    left.get("width").and_then(Value::as_i64) == right.get("width").and_then(Value::as_i64)
        && left.get("height").and_then(Value::as_i64) == right.get("height").and_then(Value::as_i64)
        && match (refresh_hz(left), refresh_hz(right)) {
            (Some(a), Some(b)) => (a - b).abs() < 0.001,
            _ => false,
        }
}

fn refresh_hz(mode: &Map<String, Value>) -> Option<f64> {
    let value = mode
        .get("refresh_rate")
        .or_else(|| mode.get("refresh_millihz"))?;
    let mut number = value.as_f64()?;
    if number >= 1000.0 {
        number /= 1000.0;
    }
    (number.is_finite() && number > 0.0).then_some((number * 1000.0).round() / 1000.0)
}

fn ac_online() -> Option<bool> {
    let entries = fs::read_dir("/sys/class/power_supply").ok()?;
    let mut values = Vec::new();
    for entry in entries.flatten() {
        let path = entry.path();
        let kind = read_trimmed(&path.join("type"));
        if !matches!(kind.as_deref(), Some("Mains" | "USB" | "USB_C")) {
            continue;
        }
        if let Some(value) = read_u64(&path.join("online")) {
            values.push(value != 0);
        }
    }
    if values.is_empty() {
        None
    } else {
        Some(values.into_iter().any(|value| value))
    }
}

fn settings_path() -> PathBuf {
    config_home().join("powerdeck/saver.json")
}

fn runtime_state_path() -> PathBuf {
    state_home().join("powerdeck/saver-state.json")
}

fn config_home() -> PathBuf {
    if let Some(root) = std::env::var_os("XDG_CONFIG_HOME") {
        return PathBuf::from(root);
    }
    home_dir().join(".config")
}

fn state_home() -> PathBuf {
    if let Some(root) = std::env::var_os("XDG_STATE_HOME") {
        return PathBuf::from(root);
    }
    home_dir().join(".local/state")
}

fn home_dir() -> PathBuf {
    std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}

fn load_settings() -> SaverSettings {
    let Ok(text) = fs::read_to_string(settings_path()) else {
        return SaverSettings::default();
    };
    serde_json::from_str::<SaverSettings>(&text)
        .ok()
        .filter(|settings| settings.validate().is_ok())
        .unwrap_or_default()
}

fn save_settings(settings: &SaverSettings) -> std::io::Result<()> {
    atomic_json_write(
        &settings_path(),
        &serde_json::to_value(settings).map_err(io_other)?,
    )
}

fn load_runtime_state(settings: SaverSettings) -> AgentState {
    let path = runtime_state_path();
    let value = fs::read_to_string(path)
        .ok()
        .and_then(|text| serde_json::from_str::<Value>(&text).ok())
        .unwrap_or(Value::Null);
    AgentState {
        settings,
        active: value
            .get("active")
            .and_then(Value::as_bool)
            .unwrap_or(false),
        activation: value
            .get("activation")
            .and_then(Value::as_str)
            .map(str::to_owned),
        ledger: ledger_from_json(&value),
        last_on_ac: value.get("last_on_ac").and_then(Value::as_bool),
        last_error: value
            .get("last_error")
            .and_then(Value::as_str)
            .map(str::to_owned),
    }
}

fn persist_runtime_state(state: &AgentState) -> Result<(), String> {
    persist_snapshot(
        state.active,
        state.activation.as_deref(),
        state.last_on_ac,
        &state.ledger,
        state.last_error.as_deref(),
    )
}

fn persist_snapshot(
    active: bool,
    activation: Option<&str>,
    last_on_ac: Option<bool>,
    ledger: &Ledger,
    last_error: Option<&str>,
) -> Result<(), String> {
    let value = json!({
        "active": active,
        "activation": activation,
        "last_on_ac": last_on_ac,
        "changes": ledger_json(ledger),
        "last_error": last_error,
    });
    atomic_json_write(&runtime_state_path(), &value).map_err(|error| error.to_string())
}

fn ledger_json(ledger: &Ledger) -> Value {
    let mut changes = BTreeMap::<String, Value>::new();
    if let Some(owned) = &ledger.brightness {
        changes.insert(
            "brightness".to_owned(),
            json!({"before": owned.previous, "applied": owned.applied}),
        );
    }
    if let Some(owned) = &ledger.display {
        changes.insert(
            "display".to_owned(),
            json!({
                "before": {"connector": owned.connector, "mode": owned.previous_mode},
                "applied": {"connector": owned.connector, "mode": owned.applied_mode},
            }),
        );
    }
    if let Some(owned) = &ledger.power_profile {
        changes.insert(
            "power_profile".to_owned(),
            json!({"before": owned.previous, "applied": owned.applied}),
        );
    }
    if let Some(owned) = &ledger.thermal_profile {
        changes.insert(
            "thermal_profile".to_owned(),
            json!({"before": owned.previous, "applied": owned.applied}),
        );
    }
    if let Some(owned) = &ledger.cpu_policy {
        changes.insert(
            "cpu_policy".to_owned(),
            json!({
                "before": {
                    "disable_turbo": owned.previous.disable_turbo,
                    "max_performance_percent": owned.previous.max_performance_percent,
                },
                "applied": {
                    "disable_turbo": owned.applied.disable_turbo,
                    "max_performance_percent": owned.applied.max_performance_percent,
                },
            }),
        );
    }
    if let Some(owned) = &ledger.keyboard_backlight {
        changes.insert(
            "keyboard_backlight".to_owned(),
            json!({"before": owned.previous, "applied": owned.applied}),
        );
    }
    if let Some(owned) = &ledger.audio_muted {
        changes.insert(
            "audio_muted".to_owned(),
            json!({"before": owned.previous, "applied": owned.applied}),
        );
    }
    json!(changes)
}

fn ledger_from_json(root: &Value) -> Ledger {
    let Some(changes) = root.get("changes").and_then(Value::as_object) else {
        return Ledger::default();
    };
    let brightness_device = first_backlight(Path::new("/sys/class/backlight"), |_| true);
    let keyboard_device = first_backlight(Path::new("/sys/class/leds"), |name| {
        name.to_ascii_lowercase().contains("kbd")
    });

    Ledger {
        brightness: numeric_change(changes.get("brightness")).and_then(|(previous, applied)| {
            brightness_device.as_ref().map(|device| OwnedBacklight {
                device: device.name.clone(),
                previous,
                applied,
            })
        }),
        display: object_change(changes.get("display")).and_then(|(before, applied)| {
            Some(OwnedDisplay {
                connector: before.get("connector")?.as_str()?.to_owned(),
                previous_mode: before.get("mode")?.as_str()?.to_owned(),
                applied_mode: applied.get("mode")?.as_str()?.to_owned(),
            })
        }),
        power_profile: string_change(changes.get("power_profile")),
        thermal_profile: string_change(changes.get("thermal_profile")),
        cpu_policy: object_change(changes.get("cpu_policy")).and_then(|(before, applied)| {
            Some(OwnedCpuPolicy {
                previous: cpu_policy_from_value(before)?,
                applied: cpu_policy_from_value(applied)?,
            })
        }),
        keyboard_backlight: numeric_change(changes.get("keyboard_backlight")).and_then(
            |(previous, applied)| {
                keyboard_device.as_ref().map(|device| OwnedBacklight {
                    device: device.name.clone(),
                    previous,
                    applied,
                })
            },
        ),
        audio_muted: bool_change(changes.get("audio_muted")),
    }
}

fn numeric_change(value: Option<&Value>) -> Option<(u64, u64)> {
    let value = value?.as_object()?;
    Some((
        value.get("before")?.as_u64()?,
        value.get("applied")?.as_u64()?,
    ))
}

fn string_change(value: Option<&Value>) -> Option<OwnedValue<String>> {
    let value = value?.as_object()?;
    Some(OwnedValue {
        previous: value.get("before")?.as_str()?.to_owned(),
        applied: value.get("applied")?.as_str()?.to_owned(),
    })
}

fn bool_change(value: Option<&Value>) -> Option<OwnedValue<bool>> {
    let value = value?.as_object()?;
    Some(OwnedValue {
        previous: value.get("before")?.as_bool()?,
        applied: value.get("applied")?.as_bool()?,
    })
}

type ObjectChange<'a> = (&'a Map<String, Value>, &'a Map<String, Value>);

fn object_change(value: Option<&Value>) -> Option<ObjectChange<'_>> {
    let value = value?.as_object()?;
    Some((
        value.get("before")?.as_object()?,
        value.get("applied")?.as_object()?,
    ))
}

fn cpu_policy_from_value(value: &Map<String, Value>) -> Option<CpuPolicy> {
    Some(CpuPolicy {
        disable_turbo: value.get("disable_turbo")?.as_bool()?,
        max_performance_percent: u8::try_from(value.get("max_performance_percent")?.as_u64()?)
            .ok()?,
    })
}

fn atomic_json_write(path: &Path, value: &Value) -> std::io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let temp = path.with_extension(format!("tmp-{}", std::process::id()));
    let bytes = serde_json::to_vec_pretty(value).map_err(io_other)?;
    fs::write(&temp, bytes)?;
    fs::rename(temp, path)
}

fn io_other(error: serde_json::Error) -> std::io::Error {
    std::io::Error::other(error)
}

fn read_trimmed(path: &Path) -> Option<String> {
    fs::read_to_string(path)
        .ok()
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty())
}

fn read_u64(path: &Path) -> Option<u64> {
    read_trimmed(path)?.parse::<u64>().ok()
}

fn command_exists(command: &str) -> bool {
    std::env::var_os("PATH")
        .is_some_and(|paths| std::env::split_paths(&paths).any(|path| path.join(command).is_file()))
}

fn command_process(command: &str) -> Command {
    let mut process = Command::new(command);
    process.stdin(Stdio::null());
    if command == "niri" && std::env::var_os("NIRI_SOCKET").is_none() {
        if let Some(socket) = find_niri_socket() {
            process.env("NIRI_SOCKET", socket);
        }
    }
    process
}

fn find_niri_socket() -> Option<PathBuf> {
    let root = std::env::var_os("XDG_RUNTIME_DIR").map(PathBuf::from)?;
    let mut sockets: Vec<PathBuf> = fs::read_dir(root)
        .ok()?
        .flatten()
        .map(|entry| entry.path())
        .filter(|path| {
            path.file_name()
                .and_then(|name| name.to_str())
                .is_some_and(|name| name.starts_with("niri.") && name.ends_with(".sock"))
        })
        .collect();
    sockets.sort();
    sockets.pop()
}

async fn command_stdout(command: &str, args: &[&str]) -> Result<String, String> {
    let mut process = command_process(command);
    process.args(args);
    let output = timeout(COMMAND_TIMEOUT, process.output())
        .await
        .map_err(|_| format!("{command} timed out"))?
        .map_err(|error| format!("{command} failed to start: {error}"))?;
    if !output.status.success() {
        let detail = String::from_utf8_lossy(&output.stderr).trim().to_owned();
        return Err(format!(
            "{command} failed: {}",
            if detail.is_empty() {
                output.status.to_string()
            } else {
                detail
            }
        ));
    }
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

async fn run_command(command: &str, args: &[&str]) -> Result<(), String> {
    command_stdout(command, args).await.map(|_| ())
}

async fn audio_muted() -> Result<Option<bool>, String> {
    if !command_exists("wpctl") {
        return Ok(None);
    }
    let output = command_stdout("wpctl", &["get-volume", "@DEFAULT_AUDIO_SINK@"]).await?;
    Ok(Some(output.to_ascii_lowercase().contains("muted")))
}

fn json_value(payload: &str) -> Option<Value> {
    serde_json::from_str(payload).ok()
}

fn json_string_field(payload: &str, key: &str) -> Option<String> {
    json_value(payload)?.get(key)?.as_str().map(str::to_owned)
}

fn json_bool_field(payload: &str, key: &str) -> Option<bool> {
    json_value(payload)?.get(key)?.as_bool()
}

fn json_u8_field(payload: &str, key: &str) -> Option<u8> {
    u8::try_from(json_value(payload)?.get(key)?.as_u64()?).ok()
}

fn cpu_policy_from_json(payload: &str) -> Option<CpuPolicy> {
    Some(CpuPolicy {
        disable_turbo: json_bool_field(payload, "disable_turbo")?,
        max_performance_percent: json_u8_field(payload, "max_performance_percent")?,
    })
}

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let system_bus = zbus::Connection::system().await?;
    let state = load_runtime_state(load_settings());
    let service = AgentService {
        state: Arc::new(Mutex::new(state)),
        system_bus,
    };

    let _connection = zbus::connection::Builder::session()?
        .name(BUS_NAME)?
        .serve_at(OBJECT_PATH, service.clone())?
        .build()
        .await?;

    tokio::spawn(ac_monitor(service));
    pending::<()>().await;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn selects_same_resolution_battery_refresh_mode() {
        let payload = json!({
            "eDP-1": {
                "logical": {},
                "current_mode": 0,
                "modes": [
                    {"width": 1920, "height": 1080, "refresh_rate": 120000},
                    {"width": 1920, "height": 1080, "refresh_rate": 60000},
                    {"width": 1280, "height": 720, "refresh_rate": 60000}
                ]
            }
        });
        let (_, output) = select_internal_output(&payload).expect("internal output");
        let modes = parse_modes(output);
        let (reference, target) = select_battery_mode(&modes, 60.0).expect("60 Hz mode");
        assert_eq!(reference.label(), "1920x1080@120.000");
        assert_eq!(target.label(), "1920x1080@60.000");
    }

    #[test]
    fn ignores_disabled_internal_output() {
        let payload = json!({
            "eDP-1": {
                "logical": null,
                "current_mode": null,
                "modes": []
            }
        });
        assert!(select_internal_output(&payload).is_none());
    }

    #[test]
    fn rejects_out_of_range_keyboard_backlight_setting() {
        let settings = SaverSettings {
            keyboard_backlight_level: 101,
            ..SaverSettings::default()
        };
        assert!(settings.validate().is_err());
    }
}
