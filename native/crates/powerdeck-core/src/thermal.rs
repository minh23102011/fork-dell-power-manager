use std::path::{Path, PathBuf};

use crate::error::{ErrorKind, PowerDeckError, Result};
use crate::sysfs::{StdSysfsIo, SysfsIo};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ThermalProfile {
    Quiet,
    Cool,
    Balanced,
    Performance,
}

impl ThermalProfile {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Quiet => "quiet",
            Self::Cool => "cool",
            Self::Balanced => "balanced",
            Self::Performance => "performance",
        }
    }

    pub fn parse(value: &str) -> Result<Self> {
        match value.trim().to_ascii_lowercase().replace('-', "_").as_str() {
            "quiet" => Ok(Self::Quiet),
            "cool" => Ok(Self::Cool),
            "balanced" => Ok(Self::Balanced),
            "performance" => Ok(Self::Performance),
            _ => Err(PowerDeckError::new(
                ErrorKind::ValidationFailed,
                "thermal",
                format!("unsupported thermal profile: {value}"),
            )),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ThermalControlStatus {
    pub current_profile: Option<ThermalProfile>,
    pub available_profiles: Vec<ThermalProfile>,
    pub source: Option<&'static str>,
    pub profile_path: Option<PathBuf>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ThermalProfileApplyResult {
    pub requested_profile: ThermalProfile,
    pub previous_profile: ThermalProfile,
    pub current_profile: ThermalProfile,
    pub changed: bool,
    pub verified: bool,
    pub source: &'static str,
    pub profile_path: PathBuf,
}

#[derive(Debug, Clone)]
struct ProfileInterface {
    choices_path: PathBuf,
    profile_path: PathBuf,
    source: &'static str,
}

pub struct ThermalProfileController<I = StdSysfsIo> {
    platform_profile_root: PathBuf,
    acpi_root: PathBuf,
    io: I,
}

impl ThermalProfileController<StdSysfsIo> {
    pub fn system() -> Self {
        Self::new(
            PathBuf::from("/sys/class/platform-profile"),
            PathBuf::from("/sys/firmware/acpi"),
            StdSysfsIo,
        )
    }
}

impl<I: SysfsIo> ThermalProfileController<I> {
    pub fn new(platform_profile_root: PathBuf, acpi_root: PathBuf, io: I) -> Self {
        Self {
            platform_profile_root,
            acpi_root,
            io,
        }
    }

    fn read_text(&self, path: &Path) -> Option<String> {
        self.io.read_text(path).ok().flatten()
    }

    fn class_interfaces(&self) -> Vec<ProfileInterface> {
        let Ok(directories) = self.io.list_dirs(&self.platform_profile_root) else {
            return Vec::new();
        };
        directories
            .into_iter()
            .filter_map(|directory| {
                let profile_path = directory.join("profile");
                let choices_path = directory.join("choices");
                if !self.io.exists(&profile_path) && !self.io.exists(&choices_path) {
                    return None;
                }
                Some(ProfileInterface {
                    choices_path,
                    profile_path,
                    source: "kernel-platform-profile-class",
                })
            })
            .collect()
    }

    fn acpi_interface(&self) -> Option<ProfileInterface> {
        let profile_path = self.acpi_root.join("platform_profile");
        let choices_path = self.acpi_root.join("platform_profile_choices");
        if !self.io.exists(&profile_path) && !self.io.exists(&choices_path) {
            return None;
        }
        Some(ProfileInterface {
            choices_path,
            profile_path,
            source: "kernel-platform-profile-acpi",
        })
    }

    fn select_interface(&self) -> Option<ProfileInterface> {
        let mut interfaces = self.class_interfaces();
        if let Some(acpi) = self.acpi_interface() {
            interfaces.push(acpi);
        }
        interfaces.into_iter().find(|interface| {
            self.read_text(&interface.profile_path).is_some()
                || self.read_text(&interface.choices_path).is_some()
        })
    }

    pub fn read_status(&self) -> ThermalControlStatus {
        let Some(interface) = self.select_interface() else {
            return ThermalControlStatus {
                current_profile: None,
                available_profiles: Vec::new(),
                source: None,
                profile_path: None,
            };
        };
        let mut available = parse_profiles(self.read_text(&interface.choices_path).as_deref());
        let current = self
            .read_text(&interface.profile_path)
            .as_deref()
            .and_then(|value| ThermalProfile::parse(value).ok());
        if let Some(profile) = current.filter(|profile| !available.contains(profile)) {
            available.push(profile);
        }
        ThermalControlStatus {
            current_profile: current,
            available_profiles: available,
            source: Some(interface.source),
            profile_path: Some(interface.profile_path),
        }
    }

    fn write_profile(&self, interface: &ProfileInterface, profile: ThermalProfile) -> Result<()> {
        self.io
            .write_text(&interface.profile_path, &format!("{}\n", profile.as_str()))
            .map_err(|error| {
                PowerDeckError::from_io(
                    "thermal",
                    &interface.profile_path,
                    "write thermal profile to",
                    error,
                )
            })
    }

    pub fn apply(&self, value: &str) -> Result<ThermalProfileApplyResult> {
        let interface = self.select_interface().ok_or_else(|| {
            PowerDeckError::new(
                ErrorKind::MissingCapability,
                "thermal",
                "no kernel platform-profile interface was found",
            )
        })?;
        let available = parse_profiles(self.read_text(&interface.choices_path).as_deref());
        if available.is_empty() {
            return Err(PowerDeckError::new(
                ErrorKind::MissingCapability,
                "thermal",
                "platform-profile choices are unavailable",
            ));
        }
        let requested = ThermalProfile::parse(value)?;
        if !available.contains(&requested) {
            return Err(PowerDeckError::new(
                ErrorKind::ValidationFailed,
                "thermal",
                format!(
                    "thermal profile is not available on this machine: {}",
                    requested.as_str()
                ),
            ));
        }
        let previous = self
            .read_text(&interface.profile_path)
            .as_deref()
            .and_then(|value| ThermalProfile::parse(value).ok())
            .ok_or_else(|| {
                PowerDeckError::new(
                    ErrorKind::MissingCapability,
                    "thermal",
                    "current thermal profile could not be read safely",
                )
            })?;
        if requested == previous {
            return Ok(ThermalProfileApplyResult {
                requested_profile: requested,
                previous_profile: previous,
                current_profile: previous,
                changed: false,
                verified: true,
                source: interface.source,
                profile_path: interface.profile_path,
            });
        }

        self.write_profile(&interface, requested)?;
        let observed = self
            .read_text(&interface.profile_path)
            .as_deref()
            .and_then(|value| ThermalProfile::parse(value).ok());
        if observed == Some(requested) {
            return Ok(ThermalProfileApplyResult {
                requested_profile: requested,
                previous_profile: previous,
                current_profile: requested,
                changed: true,
                verified: true,
                source: interface.source,
                profile_path: interface.profile_path,
            });
        }

        self.write_profile(&interface, previous)?;
        let restored = self
            .read_text(&interface.profile_path)
            .as_deref()
            .and_then(|value| ThermalProfile::parse(value).ok());
        if restored != Some(previous) {
            return Err(PowerDeckError::new(
                ErrorKind::RollbackFailed,
                "thermal",
                "thermal verification failed and rollback did not restore the previous profile",
            ));
        }
        Err(PowerDeckError::new(
            ErrorKind::VerificationFailed,
            "thermal",
            "thermal verification failed; previous profile restored",
        ))
    }
}

fn parse_profiles(value: Option<&str>) -> Vec<ThermalProfile> {
    let Some(value) = value else {
        return Vec::new();
    };
    let mut profiles = Vec::new();
    for token in value.replace(['[', ']'], " ").split_whitespace() {
        if let Ok(profile) = ThermalProfile::parse(token) {
            if !profiles.contains(&profile) {
                profiles.push(profile);
            }
        }
    }
    profiles
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
        fn with_file(mut self, path: &str, value: &str) -> Self {
            self.files
                .get_mut()
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
            self.files
                .lock()
                .expect("mutex poisoned")
                .insert(path.to_path_buf(), value.trim().to_owned());
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

    #[test]
    fn applies_and_verifies_profile() {
        let io = MemoryIo::default()
            .with_dir("/platform/hw0")
            .with_file("/platform/hw0/choices", "quiet balanced performance")
            .with_file("/platform/hw0/profile", "balanced");
        let controller =
            ThermalProfileController::new(PathBuf::from("/platform"), PathBuf::from("/acpi"), io);
        let result = controller
            .apply("performance")
            .expect("apply should succeed");
        assert!(result.changed);
        assert!(result.verified);
        assert_eq!(result.previous_profile, ThermalProfile::Balanced);
        assert_eq!(result.current_profile, ThermalProfile::Performance);
    }

    #[test]
    fn rejects_profile_not_advertised_by_kernel() {
        let io = MemoryIo::default()
            .with_dir("/platform/hw0")
            .with_file("/platform/hw0/choices", "quiet balanced")
            .with_file("/platform/hw0/profile", "balanced");
        let controller =
            ThermalProfileController::new(PathBuf::from("/platform"), PathBuf::from("/acpi"), io);
        let error = controller
            .apply("performance")
            .expect_err("must reject unavailable profile");
        assert_eq!(error.kind, ErrorKind::ValidationFailed);
    }
}
