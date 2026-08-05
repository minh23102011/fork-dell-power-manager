"""Structured exception hierarchy for PowerDeck."""

from __future__ import annotations

from enum import StrEnum

from powerdeck_core.models import DiagnosticIssue, JSONValue, Severity, to_primitive


class ErrorCode(StrEnum):
    MISSING_COMMAND = "missing-command"
    MISSING_CAPABILITY = "missing-capability"
    PERMISSION_DENIED = "permission-denied"
    COMMAND_TIMEOUT = "command-timeout"
    COMMAND_FAILED = "command-failed"
    MALFORMED_OUTPUT = "malformed-output"
    SERVICE_UNAVAILABLE = "service-unavailable"
    UNSUPPORTED_HARDWARE = "unsupported-hardware"
    INVALID_CONFIGURATION = "invalid-configuration"
    VALIDATION_FAILED = "validation-failed"
    VERIFICATION_FAILED = "verification-failed"
    TRANSACTION_FAILED = "transaction-failed"
    ROLLBACK_FAILED = "rollback-failed"


class PowerDeckError(Exception):
    """Base class carrying a stable machine-readable error code."""

    default_code = ErrorCode.COMMAND_FAILED
    default_severity = Severity.ERROR

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        hint: str | None = None,
        component: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.hint = hint
        self.component = component
        self.details = details or {}

    def to_diagnostic(self, *, severity: Severity | None = None) -> DiagnosticIssue:
        primitive_details: dict[str, JSONValue] = {key: to_primitive(value) for key, value in self.details.items()}
        return DiagnosticIssue(
            code=self.code.value,
            severity=severity or self.default_severity,
            message=self.message,
            component=self.component,
            hint=self.hint,
            details=primitive_details or None,
        )


class MissingCommandError(PowerDeckError):
    default_code = ErrorCode.MISSING_COMMAND
    default_severity = Severity.WARNING


class MissingCapabilityError(PowerDeckError):
    default_code = ErrorCode.MISSING_CAPABILITY
    default_severity = Severity.WARNING


class PermissionDeniedError(PowerDeckError):
    default_code = ErrorCode.PERMISSION_DENIED


class CommandTimeoutError(PowerDeckError):
    default_code = ErrorCode.COMMAND_TIMEOUT


class CommandExecutionError(PowerDeckError):
    default_code = ErrorCode.COMMAND_FAILED


class MalformedOutputError(PowerDeckError):
    default_code = ErrorCode.MALFORMED_OUTPUT


class ServiceUnavailableError(PowerDeckError):
    default_code = ErrorCode.SERVICE_UNAVAILABLE
    default_severity = Severity.WARNING


class UnsupportedHardwareError(PowerDeckError):
    default_code = ErrorCode.UNSUPPORTED_HARDWARE
    default_severity = Severity.WARNING


class InvalidConfigurationError(PowerDeckError):
    default_code = ErrorCode.INVALID_CONFIGURATION


class ValidationError(PowerDeckError):
    default_code = ErrorCode.VALIDATION_FAILED


class StateVerificationError(PowerDeckError):
    default_code = ErrorCode.VERIFICATION_FAILED


class TransactionError(PowerDeckError):
    default_code = ErrorCode.TRANSACTION_FAILED


class RollbackError(PowerDeckError):
    default_code = ErrorCode.ROLLBACK_FAILED


__all__ = [
    "CommandExecutionError",
    "CommandTimeoutError",
    "ErrorCode",
    "InvalidConfigurationError",
    "MalformedOutputError",
    "MissingCapabilityError",
    "MissingCommandError",
    "PermissionDeniedError",
    "PowerDeckError",
    "RollbackError",
    "ServiceUnavailableError",
    "StateVerificationError",
    "TransactionError",
    "UnsupportedHardwareError",
    "ValidationError",
]
