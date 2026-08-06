"""GTK4/Libadwaita standalone PowerDeck v0.1 application."""

from __future__ import annotations

import asyncio
import sys
import threading
from collections.abc import Callable, Sequence
from importlib import import_module
from typing import Any

from powerdeck_agent.session import SessionController
from powerdeck_agent.settings import (
    SaverSettings,
    load_settings,
    save_settings,
)
from powerdeck_backends.scanner import DiscoverySnapshot, PowerDeckScanner
from powerdeck_daemon.client import SystemClient

_APPLICATION_ID = "org.powerdeck.PowerDeck"


def _load_gi() -> tuple[Any, Any, Any, Any]:
    gi = import_module("gi")
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    return (
        import_module("gi.repository.Gtk"),
        import_module("gi.repository.Adw"),
        import_module("gi.repository.Gio"),
        import_module("gi.repository.GLib"),
    )


async def _client_call(method: str, *args: object) -> dict[str, Any]:
    client = await SystemClient.connect()
    try:
        operation = getattr(client, method)
        result = await operation(*args)
        return result
    finally:
        client.disconnect()


def _selected_text(dropdown: Any) -> str:
    item = dropdown.get_selected_item()
    return "" if item is None else str(item.get_string())


def main(argv: Sequence[str] | None = None) -> int:
    try:
        Gtk, Adw, Gio, GLib = _load_gi()
    except (ImportError, ValueError) as error:
        print(
            "PowerDeck needs python-gobject, gtk4, and libadwaita.\n"
            f"Import error: {error}",
            file=sys.stderr,
        )
        return 1

    class PowerDeckApplication(Adw.Application):  # type: ignore[name-defined]
        def __init__(self) -> None:
            super().__init__(
                application_id=_APPLICATION_ID,
                flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
            )
            self.window: Any = None
            self.overlay: Any = None
            self.stack: Any = None
            self.snapshot: DiscoverySnapshot | None = None
            self.busy = False
            self.widgets: dict[str, Any] = {}

        def do_activate(self) -> None:
            if self.window is None:
                self.window = Adw.ApplicationWindow(application=self)
                self.window.set_title("PowerDeck")
                self.window.set_default_size(900, 680)
                self.window.set_size_request(540, 480)
                self._show_loading()
                self._refresh()
            self.window.present()

        def _set_content(self, content: Any) -> None:
            if self.window is None:
                raise RuntimeError("application window is not initialized")
            self.window.set_content(content)

        def _toast(self, message: str) -> None:
            if self.overlay is not None:
                self.overlay.add_toast(Adw.Toast.new(message))

        def _show_loading(self) -> None:
            box = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=16,
                halign=Gtk.Align.CENTER,
                valign=Gtk.Align.CENTER,
            )
            box.append(Gtk.Spinner(spinning=True))
            title = Gtk.Label(label="Loading PowerDeck...")
            title.add_css_class("title-2")
            box.append(title)
            self._set_content(box)

        def _refresh(self) -> None:
            if self.busy:
                return
            self.busy = True

            def worker() -> None:
                try:
                    snapshot = PowerDeckScanner().scan()
                except Exception as error:
                    GLib.idle_add(
                        self._finish_error,
                        f"{type(error).__name__}: {error}",
                    )
                    return
                GLib.idle_add(self._render, snapshot)

            threading.Thread(
                target=worker,
                name="powerdeck-refresh",
                daemon=True,
            ).start()

        def _finish_error(self, message: str) -> bool:
            self.busy = False
            self._toast(message)
            return False

        def _run_operation(
            self,
            label: str,
            operation: Callable[[], object],
        ) -> None:
            if self.busy:
                return
            self.busy = True
            self._toast(label)

            def worker() -> None:
                try:
                    operation()
                except Exception as error:
                    GLib.idle_add(
                        self._operation_done,
                        False,
                        f"{type(error).__name__}: {error}",
                    )
                    return
                GLib.idle_add(
                    self._operation_done,
                    True,
                    "Operation completed and verified.",
                )

            threading.Thread(
                target=worker,
                name="powerdeck-operation",
                daemon=True,
            ).start()

        def _operation_done(
            self,
            success: bool,
            message: str,
        ) -> bool:
            self.busy = False
            self._toast(message)
            if success:
                self._refresh()
            return False

        @staticmethod
        def _value_row(
            title: str,
            value: str,
            subtitle: str | None = None,
        ) -> Any:
            row = Adw.ActionRow()
            row.set_title(title)
            if subtitle:
                row.set_subtitle(subtitle)
            label = Gtk.Label(label=value, xalign=1.0, selectable=True)
            label.add_css_class("dim-label")
            row.add_suffix(label)
            return row

        @staticmethod
        def _button(label: str, callback: Callable[[], None]) -> Any:
            button = Gtk.Button(label=label)
            button.add_css_class("suggested-action")
            button.connect("clicked", lambda _button: callback())
            return button

        def _battery_page(self, snapshot: DiscoverySnapshot) -> Any:
            status = snapshot.status
            battery = status.batteries[0] if status.batteries else None
            page = Adw.PreferencesPage()
            page.set_title("Battery")
            page.set_description(
                "Battery condition and Dell-compatible charge controls."
            )

            group = Adw.PreferencesGroup(title="Status")
            group.add(
                self._value_row(
                    "Battery",
                    (
                        "Not detected"
                        if battery is None
                        else (
                            f"{battery.name} - "
                            f"{battery.capacity_percent}%"
                        )
                    ),
                )
            )
            group.add(
                self._value_row(
                    "Health",
                    (
                        "Unknown"
                        if battery is None
                        or battery.health_percent is None
                        else f"{battery.health_percent:.1f}%"
                    ),
                )
            )
            group.add(
                self._value_row(
                    "AC adapter",
                    (
                        "Unknown"
                        if status.on_ac_power is None
                        else (
                            "Connected"
                            if status.on_ac_power
                            else "Disconnected"
                        )
                    ),
                )
            )
            page.add(group)

            controls = Adw.PreferencesGroup(title="Charging")
            modes = [
                mode.value
                for mode in snapshot.capabilities.charge.supported_modes
            ]
            current_mode = (
                status.charge.mode.value
                if status.charge.mode is not None
                else ""
            )
            mode_row = Adw.ActionRow(title="Charging mode")
            mode_dropdown = Gtk.DropDown.new_from_strings(modes)
            if current_mode in modes:
                mode_dropdown.set_selected(modes.index(current_mode))
            mode_row.add_suffix(mode_dropdown)
            mode_row.add_suffix(
                self._button(
                    "Apply",
                    lambda: self._apply_charge_mode(mode_dropdown),
                )
            )
            controls.add(mode_row)

            interval = status.charge.interval
            threshold_row = Adw.ActionRow(
                title="Custom thresholds",
                subtitle="Start and stop charging percentages.",
            )
            start = Gtk.SpinButton.new_with_range(50, 95, 1)
            end = Gtk.SpinButton.new_with_range(55, 100, 1)
            start.set_value(
                50 if interval is None else interval.start_percent
            )
            end.set_value(
                80 if interval is None else interval.end_percent
            )
            threshold_row.add_suffix(Gtk.Label(label="Start"))
            threshold_row.add_suffix(start)
            threshold_row.add_suffix(Gtk.Label(label="End"))
            threshold_row.add_suffix(end)
            threshold_row.add_suffix(
                self._button(
                    "Apply",
                    lambda: self._apply_thresholds(start, end),
                )
            )
            controls.add(threshold_row)
            page.add(controls)
            return page

        def _thermal_page(self, snapshot: DiscoverySnapshot) -> Any:
            page = Adw.PreferencesPage()
            page.set_title("Thermal Mode")
            page.set_description(
                "Apply a kernel platform profile through powerdeckd."
            )
            status = snapshot.status
            capabilities = snapshot.capabilities

            info = Adw.PreferencesGroup(title="Current state")
            info.add(
                self._value_row(
                    "Current thermal mode",
                    (
                        "Unknown"
                        if status.thermal.current_profile is None
                        else status.thermal.current_profile.value
                    ),
                )
            )
            info.add(
                self._value_row(
                    "OS power profile",
                    status.power_manager.current_profile or "Unknown",
                )
            )
            info.add(
                self._value_row(
                    "CPU governor",
                    capabilities.cpu.current_governor or "Unknown",
                )
            )
            page.add(info)

            modes = [
                profile.value
                for profile in capabilities.thermal.supported_profiles
            ]
            current = (
                status.thermal.current_profile.value
                if status.thermal.current_profile is not None
                else ""
            )
            group = Adw.PreferencesGroup(title="Profile")
            row = Adw.ActionRow(title="Thermal mode")
            dropdown = Gtk.DropDown.new_from_strings(modes)
            if current in modes:
                dropdown.set_selected(modes.index(current))
            row.add_suffix(dropdown)
            row.add_suffix(
                self._button(
                    "Apply",
                    lambda: self._apply_thermal(dropdown),
                )
            )
            group.add(row)
            page.add(group)
            return page

        def _switch_row(
            self,
            key: str,
            title: str,
            active: bool,
        ) -> Any:
            row = Adw.ActionRow(title=title)
            widget = Gtk.Switch(active=active, valign=Gtk.Align.CENTER)
            row.add_suffix(widget)
            self.widgets[key] = widget
            return row

        def _spin_row(
            self,
            key: str,
            title: str,
            value: float,
            minimum: float,
            maximum: float,
            step: float,
        ) -> Any:
            row = Adw.ActionRow(title=title)
            widget = Gtk.SpinButton.new_with_range(
                minimum,
                maximum,
                step,
            )
            widget.set_value(value)
            row.add_suffix(widget)
            self.widgets[key] = widget
            return row

        def _combo_row(
            self,
            key: str,
            title: str,
            values: list[str],
            selected: str,
        ) -> Any:
            row = Adw.ActionRow(title=title)
            widget = Gtk.DropDown.new_from_strings(values)
            if selected in values:
                widget.set_selected(values.index(selected))
            row.add_suffix(widget)
            self.widgets[key] = widget
            return row

        def _saver_page(self) -> Any:
            settings = load_settings()
            page = Adw.PreferencesPage()
            page.set_title("Battery Saver")
            page.set_description(
                "Automatically applies session and CPU limits on battery, "
                "then restores only values still owned by PowerDeck."
            )

            general = Adw.PreferencesGroup(title="Automation")
            general.add(
                self._switch_row(
                    "enabled",
                    "Enable Battery Saver",
                    settings.enabled,
                )
            )
            general.add(
                self._switch_row(
                    "auto",
                    "Apply automatically when unplugged",
                    settings.auto_enable_on_battery,
                )
            )
            general.add(
                self._switch_row(
                    "restore",
                    "Restore when AC reconnects",
                    settings.restore_on_ac,
                )
            )
            page.add(general)

            display = Adw.PreferencesGroup(title="Display")
            display.add(
                self._spin_row(
                    "brightness",
                    "Brightness cap (%)",
                    settings.brightness_cap_percent,
                    1,
                    100,
                    1,
                )
            )
            display.add(
                self._switch_row(
                    "only_lower",
                    "Only lower brightness",
                    settings.only_lower_brightness,
                )
            )
            display.add(
                self._spin_row(
                    "refresh",
                    "Target refresh rate (Hz)",
                    settings.target_refresh_rate_hz,
                    30,
                    240,
                    1,
                )
            )
            page.add(display)

            performance = Adw.PreferencesGroup(title="Performance")
            performance.add(
                self._combo_row(
                    "power_profile",
                    "OS power profile",
                    ["power-saver", "balanced", "performance"],
                    settings.power_profile,
                )
            )
            performance.add(
                self._combo_row(
                    "saver_thermal",
                    "Thermal profile",
                    ["quiet", "cool", "balanced", "performance"],
                    settings.thermal_profile,
                )
            )
            performance.add(
                self._switch_row(
                    "turbo",
                    "Disable CPU turbo",
                    settings.disable_turbo,
                )
            )
            performance.add(
                self._spin_row(
                    "cpu_cap",
                    "Maximum CPU performance (%)",
                    settings.max_performance_percent,
                    1,
                    100,
                    1,
                )
            )
            page.add(performance)

            devices = Adw.PreferencesGroup(title="Devices")
            devices.add(
                self._spin_row(
                    "keyboard",
                    "Keyboard backlight level",
                    settings.keyboard_backlight_level,
                    0,
                    2,
                    1,
                )
            )
            devices.add(
                self._switch_row(
                    "mute",
                    "Mute audio output",
                    settings.mute_audio,
                )
            )
            page.add(devices)

            actions = Adw.PreferencesGroup(title="Actions")
            row = Adw.ActionRow(
                title="Battery Saver controls",
                subtitle="Save settings, apply immediately, or restore.",
            )
            row.add_suffix(
                self._button("Save", self._save_saver_settings)
            )
            row.add_suffix(
                self._button("Apply now", self._apply_saver)
            )
            restore = Gtk.Button(label="Restore")
            restore.connect(
                "clicked",
                lambda _button: self._restore_saver(),
            )
            row.add_suffix(restore)
            actions.add(row)
            page.add(actions)
            return page

        def _settings_from_widgets(self) -> SaverSettings:
            return SaverSettings(
                enabled=bool(self.widgets["enabled"].get_active()),
                auto_enable_on_battery=bool(
                    self.widgets["auto"].get_active()
                ),
                restore_on_ac=bool(
                    self.widgets["restore"].get_active()
                ),
                brightness_cap_percent=int(
                    self.widgets["brightness"].get_value()
                ),
                only_lower_brightness=bool(
                    self.widgets["only_lower"].get_active()
                ),
                target_refresh_rate_hz=float(
                    self.widgets["refresh"].get_value()
                ),
                power_profile=_selected_text(
                    self.widgets["power_profile"]
                ),
                thermal_profile=_selected_text(
                    self.widgets["saver_thermal"]
                ),
                disable_turbo=bool(
                    self.widgets["turbo"].get_active()
                ),
                max_performance_percent=int(
                    self.widgets["cpu_cap"].get_value()
                ),
                keyboard_backlight_level=int(
                    self.widgets["keyboard"].get_value()
                ),
                mute_audio=bool(
                    self.widgets["mute"].get_active()
                ),
            )

        def _save_saver_settings(self) -> None:
            settings = self._settings_from_widgets()
            save_settings(settings)
            self._toast("Battery Saver settings saved.")

        def _apply_saver(self) -> None:
            settings = self._settings_from_widgets()
            save_settings(settings)
            self._run_operation(
                "Applying Battery Saver...",
                lambda: SessionController().apply_now(settings),
            )

        def _restore_saver(self) -> None:
            self._run_operation(
                "Restoring previous session state...",
                lambda: SessionController().restore_now(),
            )

        def _apply_thermal(self, dropdown: Any) -> None:
            profile = _selected_text(dropdown)
            self._run_operation(
                f"Applying thermal mode {profile}...",
                lambda: asyncio.run(
                    _client_call("set_thermal_profile", profile)
                ),
            )

        def _apply_charge_mode(self, dropdown: Any) -> None:
            mode = _selected_text(dropdown)
            self._run_operation(
                f"Applying charging mode {mode}...",
                lambda: asyncio.run(
                    _client_call("set_charge_mode", mode)
                ),
            )

        def _apply_thresholds(
            self,
            start: Any,
            end: Any,
        ) -> None:
            start_value = int(start.get_value())
            end_value = int(end.get_value())
            self._run_operation(
                "Applying custom charging thresholds...",
                lambda: asyncio.run(
                    _client_call(
                        "set_charge_thresholds",
                        start_value,
                        end_value,
                    )
                ),
            )

        def _render(self, snapshot: DiscoverySnapshot) -> bool:
            self.busy = False
            self.snapshot = snapshot
            self.widgets.clear()

            stack = Adw.ViewStack()
            stack.set_vexpand(True)
            stack.add_titled(
                self._battery_page(snapshot),
                "battery",
                "Battery",
            )
            stack.add_titled(
                self._thermal_page(snapshot),
                "thermal",
                "Thermal Mode",
            )
            stack.add_titled(
                self._saver_page(),
                "saver",
                "Battery Saver",
            )
            self.stack = stack

            switcher = Adw.ViewSwitcher()
            switcher.set_stack(stack)
            switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)

            refresh = Gtk.Button(
                icon_name="view-refresh-symbolic",
                tooltip_text="Refresh hardware state",
            )
            refresh.connect(
                "clicked",
                lambda _button: self._refresh(),
            )

            header = Adw.HeaderBar()
            header.set_title_widget(switcher)
            header.pack_end(refresh)

            switcher_bar = Adw.ViewSwitcherBar()
            switcher_bar.set_stack(stack)
            switcher_bar.set_reveal(True)

            content = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
            )
            content.append(stack)
            content.append(switcher_bar)

            toolbar = Adw.ToolbarView()
            toolbar.add_top_bar(header)
            toolbar.set_content(content)

            overlay = Adw.ToastOverlay()
            overlay.set_child(toolbar)
            self.overlay = overlay
            self._set_content(overlay)
            return False

    app = PowerDeckApplication()
    return int(app.run(list(sys.argv if argv is None else argv)))


if __name__ == "__main__":
    raise SystemExit(main())
