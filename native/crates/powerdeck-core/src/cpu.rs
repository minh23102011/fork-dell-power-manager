use std::path::{Path, PathBuf};

use crate::error::{ErrorKind, PowerDeckError, Result};
use crate::sysfs::{StdSysfsIo, SysfsIo};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CpuPolicyStatus {
    pub disable_turbo: Option<bool>,
    pub max_performance_percent: Option<u8>,
    pub source: Option<&'static str>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CpuPolicyApplyResult {
    pub previous_disable_turbo: bool,
    pub previous_max_performance_percent: u8,
    pub current_disable_turbo: bool,
    pub current_max_performance_percent: u8,
    pub changed: bool,
    pub verified: bool,
    pub source: &'static str,
}

pub struct CpuPolicyController<I = StdSysfsIo> {
    root: PathBuf,
    io: I,
}

impl CpuPolicyController<StdSysfsIo> {
    pub fn system() -> Self {
        Self::new(
            PathBuf::from("/sys/devices/system/cpu/intel_pstate"),
            StdSysfsIo,
        )
    }
}

impl<I: SysfsIo> CpuPolicyController<I> {
    pub fn new(root: PathBuf, io: I) -> Self {
        Self { root, io }
    }

    fn no_turbo_path(&self) -> PathBuf {
        self.root.join("no_turbo")
    }

    fn max_perf_path(&self) -> PathBuf {
        self.root.join("max_perf_pct")
    }

    fn read_text(&self, path: &Path) -> Option<String> {
        self.io.read_text(path).ok().flatten()
    }

    pub fn read_status(&self) -> CpuPolicyStatus {
        let disable_turbo = self
            .read_text(&self.no_turbo_path())
            .and_then(|value| value.parse::<u8>().ok())
            .map(|value| value != 0);
        let maximum = self
            .read_text(&self.max_perf_path())
            .and_then(|value| value.parse::<u8>().ok());
        let source = if disable_turbo.is_some() && maximum.is_some() {
            Some("intel_pstate")
        } else {
            None
        };
        CpuPolicyStatus {
            disable_turbo,
            max_performance_percent: maximum,
            source,
        }
    }

    fn write_value(&self, path: &Path, value: u8) -> Result<()> {
        self.io
            .write_text(path, &format!("{value}\n"))
            .map_err(|error| PowerDeckError::from_io("cpu", path, "write", error))
    }

    pub fn apply(
        &self,
        disable_turbo: bool,
        max_performance_percent: u8,
    ) -> Result<CpuPolicyApplyResult> {
        if !(1..=100).contains(&max_performance_percent) {
            return Err(PowerDeckError::new(
                ErrorKind::ValidationFailed,
                "cpu",
                "maximum CPU performance must be between 1 and 100",
            ));
        }
        let before = self.read_status();
        let previous_disable_turbo = before.disable_turbo.ok_or_else(|| {
            PowerDeckError::new(
                ErrorKind::MissingCapability,
                "cpu",
                "Intel P-state turbo control is unavailable",
            )
        })?;
        let previous_max = before.max_performance_percent.ok_or_else(|| {
            PowerDeckError::new(
                ErrorKind::MissingCapability,
                "cpu",
                "Intel P-state maximum-performance control is unavailable",
            )
        })?;

        if previous_disable_turbo == disable_turbo && previous_max == max_performance_percent {
            return Ok(CpuPolicyApplyResult {
                previous_disable_turbo,
                previous_max_performance_percent: previous_max,
                current_disable_turbo: disable_turbo,
                current_max_performance_percent: max_performance_percent,
                changed: false,
                verified: true,
                source: "intel_pstate",
            });
        }

        self.write_value(&self.no_turbo_path(), u8::from(disable_turbo))?;
        if let Err(error) = self.write_value(&self.max_perf_path(), max_performance_percent) {
            let _ = self.write_value(&self.no_turbo_path(), u8::from(previous_disable_turbo));
            return Err(error);
        }

        let after = self.read_status();
        if after.disable_turbo == Some(disable_turbo)
            && after.max_performance_percent == Some(max_performance_percent)
        {
            return Ok(CpuPolicyApplyResult {
                previous_disable_turbo,
                previous_max_performance_percent: previous_max,
                current_disable_turbo: disable_turbo,
                current_max_performance_percent: max_performance_percent,
                changed: true,
                verified: true,
                source: "intel_pstate",
            });
        }

        self.write_value(&self.max_perf_path(), previous_max)?;
        self.write_value(&self.no_turbo_path(), u8::from(previous_disable_turbo))?;
        let restored = self.read_status();
        if restored != before {
            return Err(PowerDeckError::new(
                ErrorKind::RollbackFailed,
                "cpu",
                "CPU policy verification failed and rollback failed",
            ));
        }
        Err(PowerDeckError::new(
            ErrorKind::VerificationFailed,
            "cpu",
            "CPU policy verification failed; previous values restored",
        ))
    }
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;
    use std::io;
    use std::path::{Path, PathBuf};
    use std::sync::Mutex;

    use super::*;

    #[derive(Default)]
    struct MemoryIo {
        files: Mutex<HashMap<PathBuf, String>>,
    }

    impl MemoryIo {
        fn with_file(self, path: &str, value: &str) -> Self {
            self.files
                .lock()
                .expect("mutex poisoned")
                .insert(PathBuf::from(path), value.to_owned());
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
        }

        fn list_dirs(&self, _root: &Path) -> io::Result<Vec<PathBuf>> {
            Ok(Vec::new())
        }
    }

    #[test]
    fn applies_and_verifies_cpu_policy() {
        let io = MemoryIo::default()
            .with_file("/intel/no_turbo", "0")
            .with_file("/intel/max_perf_pct", "100");
        let controller = CpuPolicyController::new(PathBuf::from("/intel"), io);
        let result = controller.apply(true, 70).expect("apply should succeed");
        assert!(result.changed);
        assert!(result.current_disable_turbo);
        assert_eq!(result.current_max_performance_percent, 70);
    }

    #[test]
    fn rejects_invalid_percentage() {
        let io = MemoryIo::default()
            .with_file("/intel/no_turbo", "0")
            .with_file("/intel/max_perf_pct", "100");
        let controller = CpuPolicyController::new(PathBuf::from("/intel"), io);
        let error = controller
            .apply(false, 0)
            .expect_err("zero must be rejected");
        assert_eq!(error.kind, ErrorKind::ValidationFailed);
    }
}
