use std::fmt;
use std::io;
use std::path::Path;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ErrorKind {
    MissingCapability,
    PermissionDenied,
    CommandFailed,
    ValidationFailed,
    VerificationFailed,
    RollbackFailed,
}

impl ErrorKind {
    pub const fn code(self) -> &'static str {
        match self {
            Self::MissingCapability => "missing-capability",
            Self::PermissionDenied => "permission-denied",
            Self::CommandFailed => "command-failed",
            Self::ValidationFailed => "validation-failed",
            Self::VerificationFailed => "verification-failed",
            Self::RollbackFailed => "rollback-failed",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PowerDeckError {
    pub kind: ErrorKind,
    pub component: &'static str,
    pub message: String,
}

impl PowerDeckError {
    pub fn new(kind: ErrorKind, component: &'static str, message: impl Into<String>) -> Self {
        Self {
            kind,
            component,
            message: message.into(),
        }
    }

    pub fn from_io(component: &'static str, path: &Path, action: &str, error: io::Error) -> Self {
        let kind = if error.kind() == io::ErrorKind::PermissionDenied {
            ErrorKind::PermissionDenied
        } else {
            ErrorKind::CommandFailed
        };
        Self::new(
            kind,
            component,
            format!("{action} {} failed: {error}", path.display()),
        )
    }
}

impl fmt::Display for PowerDeckError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.component, self.message)
    }
}

impl std::error::Error for PowerDeckError {}

pub type Result<T> = std::result::Result<T, PowerDeckError>;
