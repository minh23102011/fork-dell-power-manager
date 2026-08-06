"""Polkit authorization through the system D-Bus authority."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from dbus_next import Variant
from dbus_next.aio import MessageBus
from dbus_next.errors import DBusError
from dbus_next.message import Message

from powerdeck_core.errors import ServiceUnavailableError

_POLKIT_NAME = "org.freedesktop.PolicyKit1"
_POLKIT_PATH = "/org/freedesktop/PolicyKit1/Authority"
_POLKIT_INTERFACE = "org.freedesktop.PolicyKit1.Authority"
_ALLOW_USER_INTERACTION = 1


def parse_authorization_reply(
    body: Sequence[object],
) -> tuple[bool, bool, dict[str, str]]:
    """Parse the `(bba{ss})` result returned by CheckAuthorization."""

    result: Sequence[object] = (
        cast(Sequence[object], body[0])
        if len(body) == 1
        and isinstance(body[0], list | tuple)
        else body
    )

    if len(result) != 3:
        raise ValueError("invalid polkit authorization result")

    is_authorized, is_challenge, details = result
    if not isinstance(is_authorized, bool):
        raise ValueError("invalid polkit is_authorized value")
    if not isinstance(is_challenge, bool):
        raise ValueError("invalid polkit is_challenge value")
    if not isinstance(details, dict):
        raise ValueError("invalid polkit details value")
    if not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in details.items()
    ):
        raise ValueError("invalid polkit details mapping")

    return is_authorized, is_challenge, dict(details)


class PolkitAuthorizer:
    """Authorize one system-bus sender against a declared polkit action."""

    def __init__(self, bus: MessageBus) -> None:
        self.bus = bus

    async def authorize(
        self,
        sender: str,
        action_id: str,
        *,
        details: dict[str, str] | None = None,
        allow_interaction: bool = True,
    ) -> bool:
        subject = [
            "system-bus-name",
            {"name": Variant("s", sender)},
        ]
        flags = _ALLOW_USER_INTERACTION if allow_interaction else 0
        message = Message(
            destination=_POLKIT_NAME,
            path=_POLKIT_PATH,
            interface=_POLKIT_INTERFACE,
            member="CheckAuthorization",
            signature="(sa{sv})sa{ss}us",
            body=[
                subject,
                action_id,
                details or {},
                flags,
                "",
            ],
        )

        try:
            reply = await self.bus.call(message)
        except DBusError as error:
            raise ServiceUnavailableError(
                "Polkit could not complete the authorization request.",
                component="authorization",
                details={
                    "action_id": action_id,
                    "reason": str(error),
                },
            ) from error

        if reply is None:
            raise ServiceUnavailableError(
                "Polkit returned no authorization result.",
                component="authorization",
                details={"action_id": action_id},
            )

        try:
            authorized, _challenge, _details = (
                parse_authorization_reply(reply.body)
            )
        except ValueError as error:
            raise ServiceUnavailableError(
                "Polkit returned a malformed authorization result.",
                component="authorization",
                details={
                    "action_id": action_id,
                    "body": _safe_body(reply.body),
                },
            ) from error

        return authorized


def _safe_body(body: Sequence[Any]) -> list[str]:
    return [repr(item) for item in body]


__all__ = [
    "PolkitAuthorizer",
    "parse_authorization_reply",
]
