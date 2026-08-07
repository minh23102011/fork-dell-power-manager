//! Low-overhead native power and fan telemetry for PowerDeck.
//!
//! The sampler prefers kernel sysfs counters and uses the Linux `power` perf
//! PMU as a compatibility fallback. A tiny C helper owns only the
//! `perf_event_open(2)` ABI boundary; policy and sampling stay in safe Rust.

use std::fs;
use std::io;
use std::os::fd::RawFd;
use std::path::{Path, PathBuf};
use std::time::Instant;

#[derive(Debug, Clone, Default, PartialEq)]
pub struct TelemetrySample {
    pub cpu_watts: Option<f64>,
    pub gpu_watts: Option<f64>,
    pub fan_rpm: Option<u64>,
    pub cpu_source: Option<String>,
    pub gpu_source: Option<String>,
    pub fan_source: Option<String>,
}

#[derive(Debug)]
struct EnergyCounter {
    path: PathBuf,
    max_range: Option<u64>,
    previous: Option<(u64, Instant)>,
    source: String,
}

impl EnergyCounter {
    fn new(path: PathBuf, max_range: Option<u64>, source: impl Into<String>) -> Self {
        Self {
            path,
            max_range,
            previous: None,
            source: source.into(),
        }
    }

    fn sample_watts(&mut self) -> Option<f64> {
        let current = read_u64(&self.path)?;
        let now = Instant::now();
        let previous = self.previous.replace((current, now));
        let (old_energy, old_time) = previous?;
        let elapsed = now.duration_since(old_time).as_secs_f64();
        if elapsed <= 0.0 {
            return None;
        }

        let delta = if current >= old_energy {
            current - old_energy
        } else {
            let maximum = self.max_range?;
            maximum.checked_sub(old_energy)?.checked_add(current)?
        };
        Some(delta as f64 / 1_000_000.0 / elapsed)
    }
}

#[derive(Debug)]
struct PerfCounter {
    fd: RawFd,
    scale: f64,
    previous: Option<(u64, Instant)>,
    source: String,
}

unsafe extern "C" {
    fn powerdeck_perf_open(event_type: u32, config: u64, cpu: i32) -> i32;
    fn powerdeck_perf_read(fd: i32, value: *mut u64) -> i32;
}

impl PerfCounter {
    fn open(event_name: &str) -> Option<Self> {
        let root = Path::new("/sys/bus/event_source/devices/power");
        let event_type = u32::try_from(read_u64(&root.join("type"))?).ok()?;
        let event_spec = read_text(&root.join("events").join(event_name))?;
        let config = parse_simple_event_config(&event_spec)?;
        let cpu = first_cpu(read_text(&root.join("cpumask")).as_deref())?;
        let scale = read_text(&root.join("events").join(format!("{event_name}.scale")))
            .and_then(|value| value.parse::<f64>().ok())
            .unwrap_or(1.0);

        // SAFETY: `powerdeck_perf_open` is a tiny wrapper around
        // perf_event_open(2). All arguments are plain integer values and the
        // returned file descriptor is owned by this struct and closed in Drop.
        let fd = unsafe { powerdeck_perf_open(event_type, config, cpu) };
        if fd < 0 {
            return None;
        }
        Some(Self {
            fd,
            scale,
            previous: None,
            source: format!("linux-perf-power:{event_name}"),
        })
    }

    fn sample_watts(&mut self) -> Option<f64> {
        let mut raw = 0_u64;
        // SAFETY: `raw` points to valid writable memory for one u64 and `fd`
        // stays open for the lifetime of this object.
        if unsafe { powerdeck_perf_read(self.fd, &mut raw) } != 0 {
            return None;
        }
        let now = Instant::now();
        let previous = self.previous.replace((raw, now));
        let (old_raw, old_time) = previous?;
        let elapsed = now.duration_since(old_time).as_secs_f64();
        if elapsed <= 0.0 || raw < old_raw {
            return None;
        }
        Some((raw - old_raw) as f64 * self.scale / elapsed)
    }
}

impl Drop for PerfCounter {
    fn drop(&mut self) {
        // SAFETY: this struct uniquely owns `fd` after a successful open.
        unsafe {
            libc::close(self.fd);
        }
    }
}

#[derive(Debug)]
enum PowerSource {
    Energy(EnergyCounter),
    Perf(PerfCounter),
    DirectMicrowatts { path: PathBuf, source: String },
}

impl PowerSource {
    fn sample_watts(&mut self) -> Option<f64> {
        match self {
            Self::Energy(counter) => counter.sample_watts(),
            Self::Perf(counter) => counter.sample_watts(),
            Self::DirectMicrowatts { path, .. } => {
                read_u64(path).map(|value| value as f64 / 1_000_000.0)
            }
        }
    }

    fn source(&self) -> &str {
        match self {
            Self::Energy(counter) => &counter.source,
            Self::Perf(counter) => &counter.source,
            Self::DirectMicrowatts { source, .. } => source,
        }
    }
}

#[derive(Debug)]
pub struct TelemetrySampler {
    cpu: Option<PowerSource>,
    gpu: Option<PowerSource>,
}

impl Default for TelemetrySampler {
    fn default() -> Self {
        Self::new()
    }
}

impl TelemetrySampler {
    pub fn new() -> Self {
        Self {
            cpu: discover_cpu_source(),
            gpu: discover_gpu_source(),
        }
    }

    pub fn sample(&mut self) -> TelemetrySample {
        if self.cpu.is_none() {
            self.cpu = discover_cpu_source();
        }
        if self.gpu.is_none() {
            self.gpu = discover_gpu_source();
        }

        let cpu_watts = self.cpu.as_mut().and_then(PowerSource::sample_watts);
        let gpu_watts = self.gpu.as_mut().and_then(PowerSource::sample_watts);
        let fan = read_first_fan();

        TelemetrySample {
            cpu_watts,
            gpu_watts,
            fan_rpm: fan.as_ref().map(|item| item.0),
            cpu_source: self.cpu.as_ref().map(|source| source.source().to_owned()),
            gpu_source: self.gpu.as_ref().map(|source| source.source().to_owned()),
            fan_source: fan.map(|item| item.1),
        }
    }
}

fn discover_cpu_source() -> Option<PowerSource> {
    discover_rapl_package()
        .map(PowerSource::Energy)
        .or_else(|| PerfCounter::open("energy-pkg").map(PowerSource::Perf))
}

fn discover_rapl_package() -> Option<EnergyCounter> {
    let root = Path::new("/sys/class/powercap");
    let entries = fs::read_dir(root).ok()?;
    for entry in entries.flatten() {
        let path = entry.path();
        let Some(name) = read_text(&path.join("name")) else {
            continue;
        };
        let name = name.to_ascii_lowercase();
        if !name.contains("package") {
            continue;
        }
        let energy = path.join("energy_uj");
        if !energy.is_file() {
            continue;
        }
        return Some(EnergyCounter::new(
            energy,
            read_u64(&path.join("max_energy_range_uj")),
            format!("intel-rapl:{name}"),
        ));
    }
    None
}

fn discover_gpu_source() -> Option<PowerSource> {
    discover_drm_hwmon_power().or_else(|| PerfCounter::open("energy-gpu").map(PowerSource::Perf))
}

fn discover_drm_hwmon_power() -> Option<PowerSource> {
    let drm = Path::new("/sys/class/drm");
    let cards = fs::read_dir(drm).ok()?;
    for card in cards.flatten() {
        let card_path = card.path();
        let name = card_path.file_name()?.to_string_lossy();
        if !name.starts_with("card") || name.contains('-') {
            continue;
        }
        let hwmon_root = card_path.join("device/hwmon");
        let Ok(hwmons) = fs::read_dir(hwmon_root) else {
            continue;
        };
        for hwmon in hwmons.flatten() {
            let path = hwmon.path();
            for candidate in ["power1_average", "power1_input"] {
                let file = path.join(candidate);
                if file.is_file() {
                    return Some(PowerSource::DirectMicrowatts {
                        source: format!("drm-hwmon:{candidate}"),
                        path: file,
                    });
                }
            }
            let energy = path.join("energy1_input");
            if energy.is_file() {
                return Some(PowerSource::Energy(EnergyCounter::new(
                    energy,
                    read_u64(&path.join("energy1_max")),
                    "drm-hwmon:energy1_input",
                )));
            }
        }
    }
    None
}

fn read_first_fan() -> Option<(u64, String)> {
    let root = Path::new("/sys/class/hwmon");
    let mut directories: Vec<PathBuf> = fs::read_dir(root)
        .ok()?
        .flatten()
        .map(|entry| entry.path())
        .collect();
    directories.sort();

    for directory in directories {
        let Ok(entries) = fs::read_dir(&directory) else {
            continue;
        };
        let mut inputs: Vec<PathBuf> = entries
            .flatten()
            .map(|entry| entry.path())
            .filter(|path| {
                path.file_name()
                    .and_then(|name| name.to_str())
                    .is_some_and(|name| name.starts_with("fan") && name.ends_with("_input"))
            })
            .collect();
        inputs.sort();
        for input in inputs {
            if let Some(rpm) = read_u64(&input) {
                return Some((rpm, input.display().to_string()));
            }
        }
    }
    None
}

fn parse_simple_event_config(spec: &str) -> Option<u64> {
    spec.split(',').find_map(|assignment| {
        let (name, value) = assignment.trim().split_once('=')?;
        if name.trim() != "event" {
            return None;
        }
        parse_u64(value.trim())
    })
}

fn first_cpu(value: Option<&str>) -> Option<i32> {
    let first = value?.split(',').next()?.trim();
    let token = first.split('-').next()?.trim();
    token.parse::<i32>().ok()
}

fn parse_u64(value: &str) -> Option<u64> {
    if let Some(hex) = value.strip_prefix("0x") {
        u64::from_str_radix(hex, 16).ok()
    } else {
        value.parse::<u64>().ok()
    }
}

fn read_text(path: &Path) -> Option<String> {
    fs::read_to_string(path)
        .ok()
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty())
}

fn read_u64(path: &Path) -> Option<u64> {
    read_text(path)?.parse::<u64>().ok()
}

pub fn read_text_checked(path: &Path) -> io::Result<String> {
    Ok(fs::read_to_string(path)?.trim().to_owned())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_perf_event_hex_config() {
        assert_eq!(parse_simple_event_config("event=0x02"), Some(2));
    }

    #[test]
    fn parses_perf_event_with_extra_assignments() {
        assert_eq!(parse_simple_event_config("event=0x01,foo=3"), Some(1));
    }

    #[test]
    fn parses_first_cpu_from_range() {
        assert_eq!(first_cpu(Some("0-7,16-23")), Some(0));
    }
}
