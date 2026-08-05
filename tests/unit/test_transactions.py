import pytest

from powerdeck_core.errors import TransactionError
from powerdeck_core.transactions import (
    TransactionRecord,
    TransactionState,
    build_restore_plan,
    build_rollback_plan,
)


def test_restore_preserves_manual_user_change() -> None:
    transaction = TransactionRecord.create("ac-disconnected")
    transaction.add_change("brightness", before=72, applied=40)
    transaction.add_change("refresh_hz", before=120.003, applied=60.012)

    plan = build_restore_plan(
        transaction,
        {"brightness": 25, "refresh_hz": 60.012},
    )

    assert "brightness" not in plan
    assert plan["refresh_hz"] == 120.003


def test_transaction_transition_and_round_trip() -> None:
    transaction = TransactionRecord.create("ac-disconnected")
    transaction.transition(TransactionState.SNAPSHOTTING)
    transaction.transition(TransactionState.PLANNING)
    transaction.add_change("turbo", before=False, applied=True)

    restored = TransactionRecord.from_dict(transaction.to_dict())

    assert restored.transaction_id == transaction.transaction_id
    assert restored.state is TransactionState.PLANNING
    assert restored.changes["turbo"].before is False


def test_transaction_rejects_non_boolean_required() -> None:
    transaction = TransactionRecord.create("manual")
    payload = transaction.to_dict()
    payload["changes"] = {
        "brightness": {
            "key": "brightness",
            "before": 80,
            "applied": 40,
            "required": "false",
        }
    }

    with pytest.raises(TransactionError):
        TransactionRecord.from_dict(payload)


def test_transaction_rejects_empty_setting_key() -> None:
    transaction = TransactionRecord.create("manual")
    payload = transaction.to_dict()
    payload["changes"] = {
        "brightness": {
            "key": "",
            "before": 80,
            "applied": 40,
            "required": True,
        }
    }

    with pytest.raises(TransactionError):
        TransactionRecord.from_dict(payload)


def test_invalid_transition_is_rejected() -> None:
    transaction = TransactionRecord.create("manual")
    with pytest.raises(TransactionError):
        transaction.transition(TransactionState.ACTIVE)


def test_rollback_order_is_reversed() -> None:
    transaction = TransactionRecord.create("manual")
    transaction.add_change("first", before=1, applied=2)
    transaction.add_change("second", before=3, applied=4)

    assert list(build_rollback_plan(transaction)) == ["second", "first"]
