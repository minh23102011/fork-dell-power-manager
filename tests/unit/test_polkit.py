import pytest

from powerdeck_daemon.polkit import parse_authorization_reply


def test_parses_nested_polkit_reply() -> None:
    result = parse_authorization_reply(
        [[True, False, {"temporary_authorization_id": "test"}]]
    )

    assert result == (
        True,
        False,
        {"temporary_authorization_id": "test"},
    )


def test_rejects_malformed_polkit_reply() -> None:
    with pytest.raises(ValueError):
        parse_authorization_reply([[True]])
