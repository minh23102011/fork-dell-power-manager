use std::path::{Path, PathBuf};

use crate::error::{ErrorKind, PowerDeckError, Result};
use crate::sysfs::{StdSysfsIo, SysfsIo};

const SOURCE: &str = "linux-power-supply-sysfs";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ChargeMode {
    Adaptive,
    Standard,
    Express,
    PrimarilyAc,
    Custom,
}

impl ChargeMode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Adaptive => "adaptive",
            Self::Standard => "standard",
            Self::Express => "express",
            Self::PrimarilyAc => "primarily_ac",
            Self::Custom => "custom",
        }
    }

    pub fn parse(value: &str) -> Result<Self> {
        match value.trim().to_ascii_lowercase().replace('-', "_").as_str() {
            "adaptive" => Ok(Self::Adaptive),
            "standard" => Ok(Self::Standard),
            "express" => Ok(Self::Express),
            "primarily_ac" => Ok(Self::PrimarilyAc),
            "custom" => Ok(Self::Custom),
            _ => Err(PowerDeckError::new(
                ErrorKind::ValidationFailed,
                "battery",
                format!("unsupported charging mode: {value}"),
            )),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ChargeInterval {
    pub start_percent: u8,
    pub end_percent: u8,
}

impl ChargeInterval {
    pub fn validated(start_percent: u8, end_percent: u8) -> Result<Self> {
        if !(50..=95).contains(&start_percent) {
            return Err(PowerDeckError::new(
                ErrorKind::ValidationFailed,
                "battery",
                "charge start threshold must be between 50 and 95",
            ));
        }
        if !(55..=100).contains(&end_percent) {
            return Err(PowerDeckError::new(
                ErrorKind::ValidationFailed,
                "battery",
                "charge end threshold must be between 55 and 100",
            ));
        }
        if end_percent.saturating_sub(start_percent) < 5 {
            return Err(PowerDeckError::new(
                ErrorKind::ValidationFailed,
                "battery",
                "charge end threshold must be at least 5% above start threshold",
            ));
        }
        Ok(Self {
            start_percent,
            end_percent,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ChargeControlStatus {
    pub battery_name: Option<String>,
    pub current_mode: Option<ChargeMode>,
    pub available_modes: Vec<ChargeMode>,
    pub interval: Option<ChargeInterval>,
    pub source: Option<&'static str>,
    pub battery_path: Option<PathBuf>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ChargeApplyResult {
    pub battery_name: String,
    pub requested_mode: ChargeMode,
    pub previous_mode: Option<ChargeMode>,
    pub current_mode: ChargeMode,
    pub previous_interval: Option<ChargeInterval>,
    pub current_interval: Option<ChargeInterval>,
    pub changed: bool,
    pub verified: bool,
    pub source: &'static str,
}

#[derive(Debug, Clone)]
struct BatteryInterface {
    directory: PathBuf,
}

impl BatteryInterface {
    fn type_path(&self) -> PathBuf {
        self.directory.join("type")
    }

    fn legacy_mode_path(&self) -> PathBuf {
        self.directory.join("charge_type")
    }

    fn modes_path(&self) -> PathBuf {
        self.directory.join("charge_types")
    }

    fn start_path(&self) -> PathBuf {
        self.directory.join("charge_control_start_threshold")
    }

    fn end_path(&self) -> PathBuf {
        self.directory.join("charge_control_end_threshold")
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ParsedChargeTypes {
    choices: Vec<String>,
    active_raw: Option<String>,
}

impl ParsedChargeTypes {
    fn available_modes(&self) -> Vec<ChargeMode> {
        let mut modes = Vec::new();
        for raw in &self.choices {
            if let Some(mode) = mode_from_charge_type(raw).filter(|mode| !modes.contains(mode)) {
                modes.push(mode);
            }
        }
        if let Some(mode) = self
            .active_raw
            .as_deref()
            .and_then(mode_from_charge_type)
            .filter(|mode| !modes.contains(mode))
        {
            modes.push(mode);
        }
        modes
    }

    fn raw_for_mode(&self, requested: ChargeMode) -> Option<String> {
        self.choices
            .iter()
            .find(|choice| mode_from_charge_type(choice) == Some(requested))
            .cloned()
    }
}

#[derive(Debug, Clone)]
struct ModeSnapshot {
    parsed: ParsedChargeTypes,
    current_raw: Option<String>,
    current_mode: Option<ChargeMode>,
    write_path: Option<PathBuf>,
}

#[derive(Debug, Clone)]
struct ChargeSnapshot {
    mode: ModeSnapshot,
    interval: Option<ChargeInterval>,
}

pub struct SysfsChargeController<I = StdSysfsIo> {
    root: PathBuf,
    io: I,
}

impl SysfsChargeController<StdSysfsIo> {
    pub fn system() -> Self {
        Self::new(PathBuf::from("/sys/class/power_supply"), StdSysfsIo)
    }
}

impl<I: SysfsIo> SysfsChargeController<I> {
    pub fn new(root: PathBuf, io: I) -> Self {
        Self { root, io }
    }

    fn read_text(&self, path: &Path) -> Option<String> {
        self.io.read_text(path).ok().flatten()
    }

    fn interfaces(&self) -> Vec<BatteryInterface> {
        let Ok(directories) = self.io.list_dirs(&self.root) else {
            return Vec::new();
        };
        directories
            .into_iter()
            .filter_map(|directory| {
                let interface = BatteryInterface { directory };
                if self.read_text(&interface.type_path()).as_deref() != Some("Battery") {
                    return None;
                }
                if self.io.exists(&interface.modes_path())
                    || self.io.exists(&interface.legacy_mode_path())
                    || self.io.exists(&interface.start_path())
                    || self.io.exists(&interface.end_path())
                {
                    Some(interface)
                } else {
                    None
                }
            })
            .collect()
    }

    fn require_interface(&self) -> Result<BatteryInterface> {
        self.interfaces().into_iter().next().ok_or_else(|| {
            PowerDeckError::new(
                ErrorKind::MissingCapability,
                "battery",
                "no battery charge-control interface was found",
            )
        })
    }

    fn read_mode_snapshot(&self, interface: &BatteryInterface) -> ModeSnapshot {
        let parsed = parse_charge_types(self.read_text(&interface.modes_path()).as_deref());
        let legacy_raw = self.read_text(&interface.legacy_mode_path());
        let current_raw = legacy_raw.or_else(|| parsed.active_raw.clone());
        let current_mode = current_raw.as_deref().and_then(mode_from_charge_type);
        let write_path = if self.io.exists(&interface.legacy_mode_path()) {
            Some(interface.legacy_mode_path())
        } else if self.io.exists(&interface.modes_path()) {
            Some(interface.modes_path())
        } else {
            None
        };
        ModeSnapshot {
            parsed,
            current_raw,
            current_mode,
            write_path,
        }
    }

    fn read_interval(&self, interface: &BatteryInterface) -> Option<ChargeInterval> {
        let start = self
            .read_text(&interface.start_path())?
            .parse::<u8>()
            .ok()?;
        let end = self.read_text(&interface.end_path())?.parse::<u8>().ok()?;
        Some(ChargeInterval {
            start_percent: start,
            end_percent: end,
        })
    }

    fn snapshot(&self, interface: &BatteryInterface) -> ChargeSnapshot {
        ChargeSnapshot {
            mode: self.read_mode_snapshot(interface),
            interval: self.read_interval(interface),
        }
    }

    pub fn read_status(&self) -> ChargeControlStatus {
        let Some(interface) = self.interfaces().into_iter().next() else {
            return ChargeControlStatus {
                battery_name: None,
                current_mode: None,
                available_modes: Vec::new(),
                interval: None,
                source: None,
                battery_path: None,
            };
        };
        let snapshot = self.snapshot(&interface);
        ChargeControlStatus {
            battery_name: interface
                .directory
                .file_name()
                .map(|name| name.to_string_lossy().into_owned()),
            current_mode: snapshot.mode.current_mode,
            available_modes: snapshot.mode.parsed.available_modes(),
            interval: snapshot.interval,
            source: Some(SOURCE),
            battery_path: Some(interface.directory),
        }
    }

    fn write(&self, path: &Path, value: &str) -> Result<()> {
        self.io
            .write_text(path, &format!("{value}\n"))
            .map_err(|error| PowerDeckError::from_io("battery", path, "write", error))
    }

    fn require_mode_write(&self, snapshot: &ModeSnapshot) -> Result<PathBuf> {
        if snapshot.current_raw.is_none() {
            return Err(PowerDeckError::new(
                ErrorKind::MissingCapability,
                "battery",
                "active charging mode cannot be snapshotted safely",
            ));
        }
        snapshot.write_path.clone().ok_or_else(|| {
            PowerDeckError::new(
                ErrorKind::MissingCapability,
                "battery",
                "battery exposes no writable charge-mode file",
            )
        })
    }

    fn write_mode_raw(&self, snapshot: &ModeSnapshot, raw: &str) -> Result<()> {
        let path = self.require_mode_write(snapshot)?;
        self.write(&path, raw)
    }

    fn mode_matches(&self, interface: &BatteryInterface, raw: &str) -> bool {
        self.read_mode_snapshot(interface)
            .current_raw
            .is_some_and(|current| normalize_charge_type(&current) == normalize_charge_type(raw))
    }

    fn rollback_mode(&self, interface: &BatteryInterface, before: &ModeSnapshot) -> Result<()> {
        let previous = before.current_raw.as_deref().ok_or_else(|| {
            PowerDeckError::new(
                ErrorKind::RollbackFailed,
                "battery",
                "previous charging mode is unavailable for rollback",
            )
        })?;
        self.write_mode_raw(before, previous)?;
        if !self.mode_matches(interface, previous) {
            return Err(PowerDeckError::new(
                ErrorKind::RollbackFailed,
                "battery",
                "battery mode rollback verification failed",
            ));
        }
        Ok(())
    }

    pub fn apply_mode(&self, value: &str) -> Result<ChargeApplyResult> {
        let interface = self.require_interface()?;
        let before = self.snapshot(&interface);
        let requested = ChargeMode::parse(value)?;
        if !before.mode.parsed.available_modes().contains(&requested) {
            return Err(PowerDeckError::new(
                ErrorKind::ValidationFailed,
                "battery",
                format!(
                    "charging mode is not available on this machine: {}",
                    requested.as_str()
                ),
            ));
        }
        let target_raw = before.mode.parsed.raw_for_mode(requested).ok_or_else(|| {
            PowerDeckError::new(
                ErrorKind::MissingCapability,
                "battery",
                format!("charging mode is unavailable: {}", requested.as_str()),
            )
        })?;
        self.require_mode_write(&before.mode)?;

        if before.mode.current_mode == Some(requested) {
            return Ok(self.result(&interface, requested, &before, before.interval, false));
        }

        self.write_mode_raw(&before.mode, &target_raw)?;
        let after = self.snapshot(&interface);
        if after.mode.current_mode == Some(requested) {
            return Ok(self.result(&interface, requested, &before, after.interval, true));
        }
        self.rollback_mode(&interface, &before.mode)?;
        Err(PowerDeckError::new(
            ErrorKind::VerificationFailed,
            "battery",
            "battery mode verification failed; previous mode restored",
        ))
    }

    fn write_interval(
        &self,
        interface: &BatteryInterface,
        requested: ChargeInterval,
        current: ChargeInterval,
    ) -> Result<()> {
        if requested.end_percent > current.end_percent {
            self.write(&interface.end_path(), &requested.end_percent.to_string())?;
            self.write(
                &interface.start_path(),
                &requested.start_percent.to_string(),
            )?;
        } else {
            self.write(
                &interface.start_path(),
                &requested.start_percent.to_string(),
            )?;
            self.write(&interface.end_path(), &requested.end_percent.to_string())?;
        }
        Ok(())
    }

    fn rollback_custom(&self, interface: &BatteryInterface, before: &ChargeSnapshot) -> Result<()> {
        if let Some(previous_interval) = before.interval {
            let current = self.read_interval(interface).unwrap_or(previous_interval);
            self.write_interval(interface, previous_interval, current)?;
        }
        self.rollback_mode(interface, &before.mode)?;
        let restored = self.snapshot(interface);
        let mode_ok = match (
            before.mode.current_raw.as_deref(),
            restored.mode.current_raw.as_deref(),
        ) {
            (Some(previous), Some(current)) => {
                normalize_charge_type(previous) == normalize_charge_type(current)
            }
            _ => false,
        };
        if !mode_ok || restored.interval != before.interval {
            return Err(PowerDeckError::new(
                ErrorKind::RollbackFailed,
                "battery",
                "custom charging rollback failed",
            ));
        }
        Ok(())
    }

    pub fn apply_custom(&self, start_percent: u8, end_percent: u8) -> Result<ChargeApplyResult> {
        let interface = self.require_interface()?;
        let before = self.snapshot(&interface);
        let previous_interval = before.interval.ok_or_else(|| {
            PowerDeckError::new(
                ErrorKind::MissingCapability,
                "battery",
                "custom charging thresholds are unavailable",
            )
        })?;
        let requested_interval = ChargeInterval::validated(start_percent, end_percent)?;
        if !before
            .mode
            .parsed
            .available_modes()
            .contains(&ChargeMode::Custom)
        {
            return Err(PowerDeckError::new(
                ErrorKind::ValidationFailed,
                "battery",
                "custom charging mode is not available on this machine",
            ));
        }
        let target_raw = before
            .mode
            .parsed
            .raw_for_mode(ChargeMode::Custom)
            .ok_or_else(|| {
                PowerDeckError::new(
                    ErrorKind::MissingCapability,
                    "battery",
                    "custom charging mode is unavailable",
                )
            })?;
        self.require_mode_write(&before.mode)?;

        let operation = (|| -> Result<()> {
            if before.mode.current_mode != Some(ChargeMode::Custom) {
                self.write_mode_raw(&before.mode, &target_raw)?;
                if !self.mode_matches(&interface, &target_raw) {
                    return Err(PowerDeckError::new(
                        ErrorKind::VerificationFailed,
                        "battery",
                        "custom charging mode could not be activated",
                    ));
                }
            }
            let current = self.read_interval(&interface).unwrap_or(previous_interval);
            self.write_interval(&interface, requested_interval, current)
        })();

        if let Err(error) = operation {
            self.rollback_custom(&interface, &before)?;
            return Err(error);
        }

        let after = self.snapshot(&interface);
        if after.mode.current_mode == Some(ChargeMode::Custom)
            && after.interval == Some(requested_interval)
        {
            let changed = before.mode.current_mode != Some(ChargeMode::Custom)
                || before.interval != Some(requested_interval);
            return Ok(self.result(
                &interface,
                ChargeMode::Custom,
                &before,
                Some(requested_interval),
                changed,
            ));
        }
        self.rollback_custom(&interface, &before)?;
        Err(PowerDeckError::new(
            ErrorKind::VerificationFailed,
            "battery",
            "custom charging verification failed; previous settings restored",
        ))
    }

    fn result(
        &self,
        interface: &BatteryInterface,
        requested: ChargeMode,
        before: &ChargeSnapshot,
        current_interval: Option<ChargeInterval>,
        changed: bool,
    ) -> ChargeApplyResult {
        ChargeApplyResult {
            battery_name: interface
                .directory
                .file_name()
                .map(|name| name.to_string_lossy().into_owned())
                .unwrap_or_default(),
            requested_mode: requested,
            previous_mode: before.mode.current_mode,
            current_mode: requested,
            previous_interval: before.interval,
            current_interval,
            changed,
            verified: true,
            source: SOURCE,
        }
    }
}

fn normalize_charge_type(value: &str) -> String {
    let mut normalized = String::new();
    let mut pending_separator = false;
    for character in value.trim().chars().flat_map(char::to_lowercase) {
        if character.is_ascii_alphanumeric() {
            if pending_separator && !normalized.is_empty() {
                normalized.push('_');
            }
            normalized.push(character);
            pending_separator = false;
        } else {
            pending_separator = true;
        }
    }
    normalized.trim_matches('_').to_owned()
}

fn mode_from_charge_type(value: &str) -> Option<ChargeMode> {
    match normalize_charge_type(value).as_str() {
        "adaptive" => Some(ChargeMode::Adaptive),
        "standard" | "normal" => Some(ChargeMode::Standard),
        "fast" | "express" | "express_charge" | "expresscharge" => Some(ChargeMode::Express),
        "primarily_ac" | "primarilyac" | "ac" => Some(ChargeMode::PrimarilyAc),
        "custom" => Some(ChargeMode::Custom),
        _ => None,
    }
}

fn parse_charge_types(text: Option<&str>) -> ParsedChargeTypes {
    let Some(text) = text else {
        return ParsedChargeTypes {
            choices: Vec::new(),
            active_raw: None,
        };
    };
    let active_raw = text.find('[').and_then(|start| {
        let remainder = &text[start + 1..];
        remainder.find(']').and_then(|end| {
            let value = remainder[..end].trim();
            (!value.is_empty()).then(|| value.to_owned())
        })
    });
    let cleaned = text.replace(['[', ']', ','], " ");
    let mut choices = Vec::new();
    for token in cleaned.split_whitespace() {
        if !choices.iter().any(|choice| choice == token) {
            choices.push(token.to_owned());
        }
    }
    let active_raw = active_raw.or_else(|| {
        if choices.len() == 1 {
            choices.first().cloned()
        } else {
            None
        }
    });
    ParsedChargeTypes {
        choices,
        active_raw,
    }
}

#[cfg(test)]
mod tests {
    use std::collections::{HashMap, HashSet};
    use std::io;
    use std::path::{Path, PathBuf};
    use std::sync::Mutex;

    use super::*;

    #[derive(Default)]
    struct MemoryIo {
        files: Mutex<HashMap<PathBuf, String>>,
        dirs: HashSet<PathBuf>,
    }

    impl MemoryIo {
        fn with_file(self, path: &str, value: &str) -> Self {
            self.files
                .lock()
                .expect("mutex poisoned")
                .insert(PathBuf::from(path), value.to_owned());
            self
        }

        fn with_dir(mut self, path: &str) -> Self {
            self.dirs.insert(PathBuf::from(path));
            self
        }
    }

    impl SysfsIo for MemoryIo {
        fn read_text(&self, path: &Path) -> io::Result<Option<String>> {
            Ok(self
                .files
                .lock()
                .expect("mutex poisoned")
                .get(path)
                .cloned())
        }

        fn write_text(&self, path: &Path, value: &str) -> io::Result<()> {
            let value = value.trim();
            let mut files = self.files.lock().expect("mutex poisoned");
            if path.file_name().and_then(|name| name.to_str()) == Some("charge_types") {
                let current = files.get(path).cloned().unwrap_or_default();
                let parsed = parse_charge_types(Some(&current));
                if parsed.choices.len() > 1 {
                    let rendered = parsed
                        .choices
                        .iter()
                        .map(|choice| {
                            if normalize_charge_type(choice) == normalize_charge_type(value) {
                                format!("[{choice}]")
                            } else {
                                choice.clone()
                            }
                        })
                        .collect::<Vec<_>>()
                        .join(" ");
                    files.insert(path.to_path_buf(), rendered);
                    return Ok(());
                }
            }
            files.insert(path.to_path_buf(), value.to_owned());
            Ok(())
        }

        fn exists(&self, path: &Path) -> bool {
            self.files
                .lock()
                .expect("mutex poisoned")
                .contains_key(path)
                || self.dirs.contains(path)
        }

        fn list_dirs(&self, root: &Path) -> io::Result<Vec<PathBuf>> {
            let mut result: Vec<_> = self
                .dirs
                .iter()
                .filter(|path| path.parent() == Some(root))
                .cloned()
                .collect();
            result.sort();
            Ok(result)
        }
    }

    fn controller() -> SysfsChargeController<MemoryIo> {
        let io = MemoryIo::default()
            .with_dir("/power/BAT0")
            .with_file("/power/BAT0/type", "Battery")
            .with_file(
                "/power/BAT0/charge_types",
                "Trickle Fast Standard Adaptive [Custom]",
            )
            .with_file("/power/BAT0/charge_control_start_threshold", "60")
            .with_file("/power/BAT0/charge_control_end_threshold", "80");
        SysfsChargeController::new(PathBuf::from("/power"), io)
    }

    #[test]
    fn maps_firmware_aliases_without_losing_raw_choices() {
        let parsed = parse_charge_types(Some("Trickle Fast Standard Adaptive [Custom]"));
        assert_eq!(parsed.active_raw.as_deref(), Some("Custom"));
        assert_eq!(
            parsed.raw_for_mode(ChargeMode::Express).as_deref(),
            Some("Fast")
        );
        assert!(parsed.available_modes().contains(&ChargeMode::Custom));
    }

    #[test]
    fn applies_and_verifies_mode() {
        let controller = controller();
        let result = controller
            .apply_mode("express")
            .expect("mode apply should succeed");
        assert!(result.changed);
        assert_eq!(result.previous_mode, Some(ChargeMode::Custom));
        assert_eq!(result.current_mode, ChargeMode::Express);
    }

    #[test]
    fn applies_custom_thresholds_transactionally() {
        let controller = controller();
        let result = controller
            .apply_custom(65, 85)
            .expect("custom thresholds should apply");
        assert!(result.changed);
        assert_eq!(
            result.current_interval,
            Some(ChargeInterval {
                start_percent: 65,
                end_percent: 85,
            })
        );
    }

    #[test]
    fn rejects_too_small_custom_gap() {
        let controller = controller();
        let error = controller
            .apply_custom(70, 73)
            .expect_err("gap below five must fail");
        assert_eq!(error.kind, ErrorKind::ValidationFailed);
    }
}
