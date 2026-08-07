//! Native PowerDeck privileged-control core.
//!
//! Phase 1 intentionally has no D-Bus or GUI dependencies. The goal is to port
//! and test the transaction semantics before switching the running daemon.

pub mod battery;
pub mod cpu;
pub mod error;
pub mod sysfs;
pub mod thermal;

pub use battery::{
    ChargeApplyResult, ChargeControlStatus, ChargeInterval, ChargeMode, SysfsChargeController,
};
pub use cpu::{CpuPolicyApplyResult, CpuPolicyController, CpuPolicyStatus};
pub use error::{ErrorKind, PowerDeckError, Result};
pub use sysfs::{StdSysfsIo, SysfsIo};
pub use thermal::{
    ThermalControlStatus, ThermalProfile, ThermalProfileApplyResult, ThermalProfileController,
};
