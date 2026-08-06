"""PowerDeck privileged system D-Bus service."""

from __future__ import annotations

import asyncio
import signal
import sys
from contextlib import suppress

from dbus_next.aio import MessageBus
from dbus_next.constants import BusType, MessageType, RequestNameReply
from dbus_next.message import Message

from powerdeck_core.errors import PowerDeckError
from powerdeck_daemon.api import SystemApi
from powerdeck_daemon.constants import BUS_NAME, INTERFACE, OBJECT_PATH
from powerdeck_daemon.polkit import PolkitAuthorizer

_INTROSPECTABLE = "org.freedesktop.DBus.Introspectable"
_PEER = "org.freedesktop.DBus.Peer"
_UNKNOWN_METHOD = "org.freedesktop.DBus.Error.UnknownMethod"
_INVALID_ARGS = "org.freedesktop.DBus.Error.InvalidArgs"
_FAILED = "org.powerdeck.Error.Failed"

_INTROSPECTION_XML = f"""\
<!DOCTYPE node PUBLIC
  "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
  "http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
<node>
  <interface name="{INTERFACE}">
    <method name="Ping">
      <arg name="reply" type="s" direction="out"/>
    </method>
    <method name="GetThermalState">
      <arg name="state_json" type="s" direction="out"/>
    </method>
    <method name="SetThermalProfile">
      <arg name="profile" type="s" direction="in"/>
      <arg name="result_json" type="s" direction="out"/>
    </method>
    <method name="GetChargeState">
      <arg name="state_json" type="s" direction="out"/>
    </method>
    <method name="SetChargeMode">
      <arg name="mode" type="s" direction="in"/>
      <arg name="result_json" type="s" direction="out"/>
    </method>
    <method name="SetChargeThresholds">
      <arg name="start_percent" type="i" direction="in"/>
      <arg name="end_percent" type="i" direction="in"/>
      <arg name="result_json" type="s" direction="out"/>
    </method>
    <method name="GetCpuState">
      <arg name="state_json" type="s" direction="out"/>
    </method>
    <method name="SetCpuPolicy">
      <arg name="disable_turbo" type="b" direction="in"/>
      <arg name="max_performance_percent" type="i" direction="in"/>
      <arg name="result_json" type="s" direction="out"/>
    </method>
  </interface>
  <interface name="{_INTROSPECTABLE}">
    <method name="Introspect">
      <arg name="xml_data" type="s" direction="out"/>
    </method>
  </interface>
  <interface name="{_PEER}">
    <method name="Ping"/>
  </interface>
</node>
"""


def _error_name(error: PowerDeckError) -> str:
    words = error.code.value.replace("-", " ").title().replace(" ", "")
    return f"org.powerdeck.Error.{words}"


class SystemService:
    def __init__(
        self,
        bus: MessageBus,
        api: SystemApi,
    ) -> None:
        self.bus = bus
        self.api = api
        self._tasks: set[asyncio.Task[None]] = set()

    def handle_message(self, message: Message) -> bool:
        if message.message_type is not MessageType.METHOD_CALL:
            return False
        if message.path != OBJECT_PATH:
            return False
        task = asyncio.create_task(self._dispatch(message))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return True

    async def _dispatch(self, message: Message) -> None:
        try:
            reply = await self._call(message)
        except PowerDeckError as error:
            reply = Message.new_error(
                message,
                _error_name(error),
                error.to_diagnostic().to_json(indent=None),
            )
        except Exception as error:
            reply = Message.new_error(
                message,
                _FAILED,
                f"{type(error).__name__}: {error}",
            )
        await self.bus.send(reply)

    @staticmethod
    def _invalid(message: Message, text: str) -> Message:
        return Message.new_error(message, _INVALID_ARGS, text)

    async def _call(self, message: Message) -> Message:
        if (
            message.interface == _INTROSPECTABLE
            and message.member == "Introspect"
        ):
            if message.signature:
                return self._invalid(message, "Introspect takes no arguments.")
            return Message.new_method_return(
                message,
                "s",
                [_INTROSPECTION_XML],
            )

        if message.interface == _PEER and message.member == "Ping":
            return Message.new_method_return(message)

        if message.interface != INTERFACE:
            return Message.new_error(
                message,
                _UNKNOWN_METHOD,
                "Unknown PowerDeck interface.",
            )

        member = message.member
        sender = message.sender or ""

        if member == "Ping" and not message.signature:
            return Message.new_method_return(message, "s", ["pong"])
        if member == "GetThermalState" and not message.signature:
            return Message.new_method_return(
                message,
                "s",
                [await self.api.get_thermal_state()],
            )
        if member == "SetThermalProfile" and message.signature == "s":
            return Message.new_method_return(
                message,
                "s",
                [
                    await self.api.set_thermal_profile(
                        sender,
                        str(message.body[0]),
                    )
                ],
            )
        if member == "GetChargeState" and not message.signature:
            return Message.new_method_return(
                message,
                "s",
                [await self.api.get_charge_state()],
            )
        if member == "SetChargeMode" and message.signature == "s":
            return Message.new_method_return(
                message,
                "s",
                [
                    await self.api.set_charge_mode(
                        sender,
                        str(message.body[0]),
                    )
                ],
            )
        if member == "SetChargeThresholds" and message.signature == "ii":
            return Message.new_method_return(
                message,
                "s",
                [
                    await self.api.set_charge_thresholds(
                        sender,
                        int(message.body[0]),
                        int(message.body[1]),
                    )
                ],
            )
        if member == "GetCpuState" and not message.signature:
            return Message.new_method_return(
                message,
                "s",
                [await self.api.get_cpu_state()],
            )
        if member == "SetCpuPolicy" and message.signature == "bi":
            return Message.new_method_return(
                message,
                "s",
                [
                    await self.api.set_cpu_policy(
                        sender,
                        bool(message.body[0]),
                        int(message.body[1]),
                    )
                ],
            )

        return Message.new_error(
            message,
            _UNKNOWN_METHOD,
            f"Unknown method or invalid signature: {member}",
        )


async def _run() -> int:
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    service = SystemService(
        bus,
        SystemApi(authorizer=PolkitAuthorizer(bus)),
    )
    bus.add_message_handler(service.handle_message)

    result = await bus.request_name(BUS_NAME)
    if result not in {
        RequestNameReply.PRIMARY_OWNER,
        RequestNameReply.ALREADY_OWNER,
    }:
        print(
            f"powerdeckd: could not own {BUS_NAME}: {result.name}",
            file=sys.stderr,
        )
        return 1

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(signum, stop_event.set)

    await stop_event.wait()
    bus.disconnect()
    return 0


def main() -> int:
    try:
        return asyncio.run(_run())
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        print(
            f"powerdeckd: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
