"""Pure transaction state and restore-ownership logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from powerdeck_core.errors import TransactionError
from powerdeck_core.models import JSONValue, SerializableModel


class TransactionState(StrEnum):
    IDLE = "idle"
    SNAPSHOTTING = "snapshotting"
    PLANNING = "planning"
    APPLYING = "applying"
    ACTIVE = "active"
    RESTORING = "restoring"
    ROLLING_BACK = "rolling-back"
    COMPLETED = "completed"
    ERROR = "error"


_ALLOWED_TRANSITIONS: dict[TransactionState, frozenset[TransactionState]] = {
    TransactionState.IDLE: frozenset({TransactionState.SNAPSHOTTING}),
    TransactionState.SNAPSHOTTING: frozenset(
        {TransactionState.PLANNING, TransactionState.ROLLING_BACK, TransactionState.ERROR}
    ),
    TransactionState.PLANNING: frozenset(
        {TransactionState.APPLYING, TransactionState.ROLLING_BACK, TransactionState.ERROR}
    ),
    TransactionState.APPLYING: frozenset(
        {TransactionState.ACTIVE, TransactionState.ROLLING_BACK, TransactionState.ERROR}
    ),
    TransactionState.ACTIVE: frozenset(
        {TransactionState.RESTORING, TransactionState.ROLLING_BACK, TransactionState.ERROR}
    ),
    TransactionState.RESTORING: frozenset(
        {TransactionState.COMPLETED, TransactionState.ERROR}
    ),
    TransactionState.ROLLING_BACK: frozenset(
        {TransactionState.COMPLETED, TransactionState.ERROR}
    ),
    TransactionState.COMPLETED: frozenset(),
    TransactionState.ERROR: frozenset(
        {TransactionState.RESTORING, TransactionState.ROLLING_BACK, TransactionState.COMPLETED}
    ),
}


@dataclass(frozen=True, slots=True)
class SettingChange(SerializableModel):
    key: str
    before: JSONValue
    applied: JSONValue
    required: bool = True


@dataclass(slots=True)
class TransactionRecord(SerializableModel):
    transaction_id: str
    trigger: str
    state: TransactionState
    started_at: datetime
    updated_at: datetime
    changes: dict[str, SettingChange] = field(default_factory=dict)
    error_messages: list[str] = field(default_factory=list)

    @classmethod
    def create(cls, trigger: str) -> "TransactionRecord":
        now = datetime.now(UTC)
        return cls(
            transaction_id=str(uuid4()),
            trigger=trigger,
            state=TransactionState.IDLE,
            started_at=now,
            updated_at=now,
        )

    def transition(self, target: TransactionState) -> None:
        allowed = _ALLOWED_TRANSITIONS[self.state]
        if target not in allowed:
            raise TransactionError(
                f"invalid transaction transition: {self.state.value} -> {target.value}",
                component="transaction",
                details={"current": self.state.value, "target": target.value},
            )
        self.state = target
        self.updated_at = datetime.now(UTC)

    def add_change(
        self,
        key: str,
        *,
        before: JSONValue,
        applied: JSONValue,
        required: bool = True,
    ) -> None:
        if not key:
            raise TransactionError("transaction setting key cannot be empty", component="transaction")
        self.changes[key] = SettingChange(
            key=key,
            before=before,
            applied=applied,
            required=required,
        )
        self.updated_at = datetime.now(UTC)

    def add_error(self, message: str) -> None:
        self.error_messages.append(message)
        self.updated_at = datetime.now(UTC)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TransactionRecord":
        try:
            changes_raw = raw.get("changes", {})
            if not isinstance(changes_raw, dict):
                raise TypeError("changes must be an object")
            changes: dict[str, SettingChange] = {}
            for key, item in changes_raw.items():
                if not isinstance(key, str) or not isinstance(item, dict):
                    raise TypeError("invalid setting change")

                item_key = item.get("key", key)
                if not isinstance(item_key, str) or not item_key:
                    raise TypeError("setting change key must be a non-empty string")

                required_raw = item.get("required", True)
                if not isinstance(required_raw, bool):
                    raise TypeError("required must be a boolean")

                changes[key] = SettingChange(
                    key=item_key,
                    before=item.get("before"),
                    applied=item.get("applied"),
                    required=required_raw,
                )
            errors_raw = raw.get("error_messages", [])
            if not isinstance(errors_raw, list) or not all(
                isinstance(item, str) for item in errors_raw
            ):
                raise TypeError("error_messages must be an array of strings")
            return cls(
                transaction_id=str(raw["transaction_id"]),
                trigger=str(raw["trigger"]),
                state=TransactionState(str(raw["state"])),
                started_at=datetime.fromisoformat(str(raw["started_at"])),
                updated_at=datetime.fromisoformat(str(raw["updated_at"])),
                changes=changes,
                error_messages=list(errors_raw),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise TransactionError(
                "invalid serialized transaction",
                component="transaction",
                details={"reason": str(error)},
            ) from error


def should_restore_setting(current: JSONValue, applied_by_powerdeck: JSONValue) -> bool:
    """PowerDeck may restore only values it still owns."""

    return current == applied_by_powerdeck


def build_restore_plan(
    transaction: TransactionRecord,
    current_values: dict[str, JSONValue],
) -> dict[str, JSONValue]:
    """Return original values that remain safe to restore."""

    plan: dict[str, JSONValue] = {}
    for key, change in transaction.changes.items():
        if key not in current_values:
            continue
        if should_restore_setting(current_values[key], change.applied):
            plan[key] = change.before
    return plan


def build_rollback_plan(transaction: TransactionRecord) -> dict[str, JSONValue]:
    """Rollback is attempted in reverse insertion order."""

    return {
        key: change.before
        for key, change in reversed(tuple(transaction.changes.items()))
    }


__all__ = [
    "SettingChange",
    "TransactionRecord",
    "TransactionState",
    "build_restore_plan",
    "build_rollback_plan",
    "should_restore_setting",
]
