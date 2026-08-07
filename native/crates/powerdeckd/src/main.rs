use std::future::pending;
use std::path::Path;
use std::sync::Mutex;

use powerdeck_core_native::{
    ChargeApplyResult, ChargeControlStatus, CpuPolicyApplyResult, CpuPolicyController,
    CpuPolicyStatus, ErrorKind, PowerDeckError, SysfsChargeController, ThermalControlStatus,
    ThermalProfileApplyResult, ThermalProfileController,
};
use powerdeck_telemetry_native::{TelemetrySample, TelemetrySampler};
use serde_json::{Value, json};
use tokio::process::Command;
use tokio::sync::Mutex as AsyncMutex;
use zbus::message::Header;
use zbus::{DBusError, interface};

const BUS_NAME: &str = "org.powerdeck.System1";
const OBJECT_PATH: &str = "/org/powerdeck/System1";
const INTERFACE: &str = "org.powerdeck.System1";
const ACTION_MANAGE_POWER: &str = "org.powerdeck.system.manage-power";

#[derive(DBusError, Debug)]
#[zbus(prefix = "org.powerdeck.Error")]
enum ServiceError {
    MissingCapability(String),
    PermissionDenied(String),
    CommandFailed(String),
    ValidationFailed(String),
    VerificationFailed(String),
    RollbackFailed(String),
    ServiceUnavailable(String),
}

impl From<PowerDeckError> for ServiceError {
    fn from(error: PowerDeckError) -> Self {
        let payload = diagnostic_json(error.kind.code(), error.component, &error.message, None);
        match error.kind {
            ErrorKind::MissingCapability => Self::MissingCapability(payload),
            ErrorKind::PermissionDenied => Self::PermissionDenied(payload),
            ErrorKind::CommandFailed => Self::CommandFailed(payload),
            ErrorKind::ValidationFailed => Self::ValidationFailed(payload),
            ErrorKind::VerificationFailed => Self::VerificationFailed(payload),
            ErrorKind::RollbackFailed => Self::RollbackFailed(payload),
        }
    }
}

struct SystemService {
    telemetry: Mutex<TelemetrySampler>,
    transaction_lock: AsyncMutex<()>,
}

impl SystemService {
    fn new() -> Self {
        Self {
            telemetry: Mutex::new(TelemetrySampler::new()),
            transaction_lock: AsyncMutex::new(()),
        }
    }

    async fn authorize(
        &self,
        header: &Header<'_>,
        operation: &str,
        details: &[(&str, String)],
    ) -> Result<(), ServiceError> {
        let sender = header.sender().ok_or_else(|| {
            ServiceError::PermissionDenied(diagnostic_json(
                "permission-denied",
                "authorization",
                "The D-Bus caller identity is unavailable.",
                Some(json!({"operation": operation})),
            ))
        })?;

        let mut command = Command::new("/usr/bin/pkcheck");
        command
            .arg("--action-id")
            .arg(ACTION_MANAGE_POWER)
            .arg("--system-bus-name")
            .arg(sender.as_str())
            .arg("--allow-user-interaction")
            .arg("--detail")
            .arg("operation")
            .arg(operation);
        for (key, value) in details {
            command.arg("--detail").arg(key).arg(value);
        }

        let output = command.output().await.map_err(|error| {
            ServiceError::ServiceUnavailable(diagnostic_json(
                "service-unavailable",
                "authorization",
                &format!("Polkit authorization could not be started: {error}"),
                Some(json!({"operation": operation})),
            ))
        })?;

        if output.status.success() {
            return Ok(());
        }

        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_owned();
        let details = json!({
            "operation": operation,
            "pkcheck_status": output.status.code(),
            "reason": stderr,
        });
        Err(ServiceError::PermissionDenied(diagnostic_json(
            "permission-denied",
            "authorization",
            "Authorization to manage laptop power settings was denied.",
            Some(details),
        )))
    }
}

#[interface(name = "org.powerdeck.System1")]
impl SystemService {
    #[zbus(name = "Ping")]
    fn ping(&self) -> &str {
        "pong"
    }

    #[zbus(name = "GetTelemetryState")]
    fn get_telemetry_state(&self) -> Result<String, ServiceError> {
        let mut sampler = self.telemetry.lock().map_err(|_| {
            ServiceError::ServiceUnavailable(diagnostic_json(
                "service-unavailable",
                "telemetry",
                "The telemetry sampler lock is poisoned.",
                None,
            ))
        })?;
        Ok(telemetry_json(&sampler.sample()).to_string())
    }

    #[zbus(name = "GetThermalState")]
    fn get_thermal_state(&self) -> String {
        thermal_status_json(&ThermalProfileController::system().read_status()).to_string()
    }

    #[zbus(name = "SetThermalProfile")]
    async fn set_thermal_profile(
        &self,
        profile: &str,
        #[zbus(header)] header: Header<'_>,
    ) -> Result<String, ServiceError> {
        self.authorize(
            &header,
            "set-thermal-profile",
            &[("profile", profile.to_owned())],
        )
        .await?;
        let _guard = self.transaction_lock.lock().await;
        let result = ThermalProfileController::system().apply(profile)?;
        Ok(thermal_apply_json(&result).to_string())
    }

    #[zbus(name = "GetChargeState")]
    fn get_charge_state(&self) -> String {
        charge_status_json(&SysfsChargeController::system().read_status()).to_string()
    }

    #[zbus(name = "SetChargeMode")]
    async fn set_charge_mode(
        &self,
        mode: &str,
        #[zbus(header)] header: Header<'_>,
    ) -> Result<String, ServiceError> {
        self.authorize(&header, "set-charge-mode", &[("mode", mode.to_owned())])
            .await?;
        let _guard = self.transaction_lock.lock().await;
        let result = SysfsChargeController::system().apply_mode(mode)?;
        Ok(charge_apply_json(&result).to_string())
    }

    #[zbus(name = "SetChargeThresholds")]
    async fn set_charge_thresholds(
        &self,
        start_percent: i32,
        end_percent: i32,
        #[zbus(header)] header: Header<'_>,
    ) -> Result<String, ServiceError> {
        let start = u8::try_from(start_percent).map_err(|_| {
            ServiceError::ValidationFailed(diagnostic_json(
                "validation-failed",
                "battery",
                "charge start threshold must be an integer between 0 and 255",
                Some(json!({"start_percent": start_percent})),
            ))
        })?;
        let end = u8::try_from(end_percent).map_err(|_| {
            ServiceError::ValidationFailed(diagnostic_json(
                "validation-failed",
                "battery",
                "charge end threshold must be an integer between 0 and 255",
                Some(json!({"end_percent": end_percent})),
            ))
        })?;
        self.authorize(
            &header,
            "set-charge-thresholds",
            &[
                ("start_percent", start_percent.to_string()),
                ("end_percent", end_percent.to_string()),
            ],
        )
        .await?;
        let _guard = self.transaction_lock.lock().await;
        let result = SysfsChargeController::system().apply_custom(start, end)?;
        Ok(charge_apply_json(&result).to_string())
    }

    #[zbus(name = "GetCpuState")]
    fn get_cpu_state(&self) -> String {
        cpu_status_json(&CpuPolicyController::system().read_status()).to_string()
    }

    #[zbus(name = "SetCpuPolicy")]
    async fn set_cpu_policy(
        &self,
        disable_turbo: bool,
        max_performance_percent: i32,
        #[zbus(header)] header: Header<'_>,
    ) -> Result<String, ServiceError> {
        let maximum = u8::try_from(max_performance_percent).map_err(|_| {
            ServiceError::ValidationFailed(diagnostic_json(
                "validation-failed",
                "cpu",
                "maximum CPU performance must be between 1 and 100",
                Some(json!({"max_performance_percent": max_performance_percent})),
            ))
        })?;
        self.authorize(
            &header,
            "set-cpu-policy",
            &[
                ("disable_turbo", disable_turbo.to_string()),
                (
                    "max_performance_percent",
                    max_performance_percent.to_string(),
                ),
            ],
        )
        .await?;
        let _guard = self.transaction_lock.lock().await;
        let result = CpuPolicyController::system().apply(disable_turbo, maximum)?;
        Ok(cpu_apply_json(&result).to_string())
    }
}

fn diagnostic_json(code: &str, component: &str, message: &str, details: Option<Value>) -> String {
    let severity = match code {
        "missing-capability" | "service-unavailable" => "warning",
        _ => "error",
    };
    json!({
        "code": code,
        "severity": severity,
        "message": message,
        "component": component,
        "hint": Value::Null,
        "details": details.unwrap_or(Value::Null),
    })
    .to_string()
}

fn telemetry_json(sample: &TelemetrySample) -> Value {
    json!({
        "cpu_watts": sample.cpu_watts,
        "gpu_watts": sample.gpu_watts,
        "fan_rpm": sample.fan_rpm,
        "cpu_source": sample.cpu_source,
        "gpu_source": sample.gpu_source,
        "fan_source": sample.fan_source,
    })
}

fn thermal_status_json(status: &ThermalControlStatus) -> Value {
    json!({
        "current_profile": status.current_profile.map(|value| value.as_str()),
        "available_profiles": status
            .available_profiles
            .iter()
            .map(|value| value.as_str())
            .collect::<Vec<_>>(),
        "source": status.source,
        "profile_path": status
            .profile_path
            .as_deref()
            .map(Path::display)
            .map(|value| value.to_string()),
    })
}

fn thermal_apply_json(result: &ThermalProfileApplyResult) -> Value {
    json!({
        "requested_profile": result.requested_profile.as_str(),
        "previous_profile": result.previous_profile.as_str(),
        "current_profile": result.current_profile.as_str(),
        "changed": result.changed,
        "verified": result.verified,
        "source": result.source,
        "profile_path": result.profile_path.display().to_string(),
    })
}

fn charge_status_json(status: &ChargeControlStatus) -> Value {
    json!({
        "battery_name": status.battery_name,
        "current_mode": status.current_mode.map(|value| value.as_str()),
        "available_modes": status
            .available_modes
            .iter()
            .map(|value| value.as_str())
            .collect::<Vec<_>>(),
        "interval": status.interval.map(|value| json!({
            "start_percent": value.start_percent,
            "end_percent": value.end_percent,
        })),
        "source": status.source,
        "battery_path": status
            .battery_path
            .as_deref()
            .map(Path::display)
            .map(|value| value.to_string()),
    })
}

fn charge_apply_json(result: &ChargeApplyResult) -> Value {
    json!({
        "battery_name": result.battery_name,
        "requested_mode": result.requested_mode.as_str(),
        "previous_mode": result.previous_mode.map(|value| value.as_str()),
        "current_mode": result.current_mode.as_str(),
        "previous_interval": result.previous_interval.map(|value| json!({
            "start_percent": value.start_percent,
            "end_percent": value.end_percent,
        })),
        "current_interval": result.current_interval.map(|value| json!({
            "start_percent": value.start_percent,
            "end_percent": value.end_percent,
        })),
        "changed": result.changed,
        "verified": result.verified,
        "source": result.source,
    })
}

fn cpu_status_json(status: &CpuPolicyStatus) -> Value {
    json!({
        "disable_turbo": status.disable_turbo,
        "max_performance_percent": status.max_performance_percent,
        "source": status.source,
    })
}

fn cpu_apply_json(result: &CpuPolicyApplyResult) -> Value {
    json!({
        "previous_disable_turbo": result.previous_disable_turbo,
        "previous_max_performance_percent": result.previous_max_performance_percent,
        "current_disable_turbo": result.current_disable_turbo,
        "current_max_performance_percent": result.current_max_performance_percent,
        "changed": result.changed,
        "verified": result.verified,
        "source": result.source,
    })
}

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let _connection = zbus::connection::Builder::system()?
        .name(BUS_NAME)?
        .serve_at(OBJECT_PATH, SystemService::new())?
        .build()
        .await?;

    eprintln!("powerdeckd-native: serving {INTERFACE} on {OBJECT_PATH}");
    pending::<()>().await;
    Ok(())
}
