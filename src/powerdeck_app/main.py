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
from powerdeck_app.theme import POWERDECK_CSS
from powerdeck_app.ui_spec import NAVIGATION
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
            self._css_provider: Any = None

        def do_activate(self) -> None:
            if self.window is None:
                self.window = Adw.ApplicationWindow(application=self)
                self.window.set_title("PowerDeck")
                self.window.set_default_size(1120, 720)
                self.window.set_size_request(920, 560)
                self._install_css()
                self._show_loading()
                self._refresh()
            self.window.present()

        def _install_css(self) -> None:
            if self.window is None:
                return
            provider = Gtk.CssProvider()
            provider.load_from_data(
                POWERDECK_CSS.encode("utf-8")
            )
            Gtk.StyleContext.add_provider_for_display(
                self.window.get_display(),
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
            self._css_provider = provider

        def _set_content(self, content: Any) -> None:
            if self.window is None:
                raise RuntimeError(
                    "application window is not initialized"
                )
            self.window.set_content(content)

        def _toast(self, message: str) -> None:
            if self.overlay is not None:
                self.overlay.add_toast(Adw.Toast.new(message))

        def _show_loading(self) -> None:
            box = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=12,
                halign=Gtk.Align.CENTER,
                valign=Gtk.Align.CENTER,
            )
            box.add_css_class("powerdeck-root")
            box.append(Gtk.Spinner(spinning=True))

            title = Gtk.Label(label="Loading PowerDeck...")
            title.add_css_class("powerdeck-page-title")
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
            _success: bool,
            message: str,
        ) -> bool:
            self.busy = False
            self._toast(message)
            self._refresh()
            return False

        @staticmethod
        def _label(
            text: str,
            css_class: str,
            *,
            wrap: bool = False,
            xalign: float = 0.0,
        ) -> Any:
            label = Gtk.Label(label=text, xalign=xalign)
            label.add_css_class(css_class)
            if wrap:
                label.set_wrap(True)
                label.set_wrap_mode(2)
            return label

        @staticmethod
        def _icon(icon_name: str, size: int = 18) -> Any:
            image = Gtk.Image.new_from_icon_name(icon_name)
            image.set_pixel_size(size)
            return image

        @staticmethod
        def _button(
            label: str,
            callback: Callable[[], None],
        ) -> Any:
            button = Gtk.Button(label=label)
            button.add_css_class("suggested-action")
            button.connect(
                "clicked",
                lambda _button: callback(),
            )
            return button

        def _row(
            self,
            title: str,
            *,
            subtitle: str | None = None,
            suffix: Any | None = None,
            tall: bool = False,
        ) -> Any:
            row = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=16,
            )
            row.add_css_class("powerdeck-card-row")
            if tall:
                row.add_css_class("powerdeck-card-row-tall")

            text = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=2,
            )
            text.set_hexpand(True)
            text.append(
                self._label(
                    title,
                    "powerdeck-row-title",
                )
            )
            if subtitle:
                text.append(
                    self._label(
                        subtitle,
                        "powerdeck-row-subtitle",
                        wrap=True,
                    )
                )
            row.append(text)

            if suffix is not None:
                row.append(suffix)
            return row

        def _value_suffix(self, value: str) -> Any:
            return self._label(
                value,
                "powerdeck-value",
                xalign=1.0,
            )

        @staticmethod
        def _separator() -> Any:
            separator = Gtk.Separator(
                orientation=Gtk.Orientation.HORIZONTAL
            )
            separator.add_css_class("powerdeck-separator")
            return separator

        def _card(self, rows: Sequence[Any]) -> Any:
            card = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=0,
            )
            card.add_css_class("powerdeck-card")

            for index, row in enumerate(rows):
                card.append(row)
                if index < len(rows) - 1:
                    card.append(self._separator())
            return card

        def _section(
            self,
            title: str,
            card: Any,
        ) -> Any:
            section = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=8,
            )
            section.append(
                self._label(
                    title,
                    "powerdeck-section-title",
                )
            )
            section.append(card)
            return section

        def _page(
            self,
            title: str,
            description: str,
        ) -> Any:
            page = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=24,
            )
            page.add_css_class("powerdeck-page")
            page.set_hexpand(True)

            heading = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=6,
            )
            heading.append(
                self._label(
                    title,
                    "powerdeck-page-title",
                )
            )
            heading.append(
                self._label(
                    description,
                    "powerdeck-page-description",
                    wrap=True,
                )
            )
            page.append(heading)
            return page

        def _scrolled_page(self, page: Any) -> Any:
            clamp = Adw.Clamp()
            clamp.set_maximum_size(1040)
            clamp.set_tightening_threshold(760)
            clamp.set_child(page)

            scroller = Gtk.ScrolledWindow()
            scroller.set_policy(
                Gtk.PolicyType.NEVER,
                Gtk.PolicyType.AUTOMATIC,
            )
            scroller.set_child(clamp)
            return scroller

        def _battery_page(
            self,
            snapshot: DiscoverySnapshot,
        ) -> Any:
            status = snapshot.status
            battery = (
                status.batteries[0]
                if status.batteries
                else None
            )
            page = self._page(
                "Battery",
                (
                    "Battery condition and Dell-compatible "
                    "charge controls."
                ),
            )

            battery_value = (
                "Not detected"
                if battery is None
                else (
                    f"{battery.name} · "
                    f"{battery.capacity_percent}%"
                )
            )
            health_value = (
                "Unknown"
                if battery is None
                or battery.health_percent is None
                else f"{battery.health_percent:.1f}%"
            )
            ac_value = (
                "Unknown"
                if status.on_ac_power is None
                else (
                    "Connected"
                    if status.on_ac_power
                    else "Disconnected"
                )
            )

            status_card = self._card(
                (
                    self._row(
                        "Battery",
                        suffix=self._value_suffix(
                            battery_value
                        ),
                    ),
                    self._row(
                        "Health",
                        suffix=self._value_suffix(
                            health_value
                        ),
                    ),
                    self._row(
                        "AC adapter",
                        suffix=self._value_suffix(ac_value),
                    ),
                )
            )
            page.append(
                self._section(
                    "Status",
                    status_card,
                )
            )

            modes = [
                mode.value
                for mode
                in snapshot.capabilities.charge.supported_modes
            ]
            current_mode = (
                status.charge.mode.value
                if status.charge.mode is not None
                else ""
            )

            mode_controls = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=8,
                valign=Gtk.Align.CENTER,
            )
            mode_dropdown = Gtk.DropDown.new_from_strings(
                modes
            )
            mode_dropdown.set_size_request(150, -1)
            if current_mode in modes:
                mode_dropdown.set_selected(
                    modes.index(current_mode)
                )
            mode_controls.append(mode_dropdown)
            mode_controls.append(
                self._button(
                    "Apply",
                    lambda: self._apply_charge_mode(
                        mode_dropdown
                    ),
                )
            )

            interval = status.charge.interval
            start = Gtk.SpinButton.new_with_range(
                50,
                95,
                1,
            )
            end = Gtk.SpinButton.new_with_range(
                55,
                100,
                1,
            )
            start.set_value(
                50
                if interval is None
                else interval.start_percent
            )
            end.set_value(
                80
                if interval is None
                else interval.end_percent
            )

            threshold_controls = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=7,
                valign=Gtk.Align.CENTER,
            )
            threshold_controls.append(
                self._label(
                    "Start",
                    "powerdeck-row-subtitle",
                )
            )
            threshold_controls.append(start)
            threshold_controls.append(
                self._label(
                    "End",
                    "powerdeck-row-subtitle",
                )
            )
            threshold_controls.append(end)
            threshold_controls.append(
                self._button(
                    "Apply",
                    lambda: self._apply_thresholds(
                        start,
                        end,
                    ),
                )
            )

            charging_card = self._card(
                (
                    self._row(
                        "Charging mode",
                        subtitle=(
                            "Select how the battery is charged."
                        ),
                        suffix=mode_controls,
                        tall=True,
                    ),
                    self._row(
                        "Custom thresholds",
                        subtitle=(
                            "Start and stop charging "
                            "percentages."
                        ),
                        suffix=threshold_controls,
                        tall=True,
                    ),
                )
            )
            page.append(
                self._section(
                    "Charging",
                    charging_card,
                )
            )

            note = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=10,
            )
            note.add_css_class("powerdeck-quiet-box")
            note.append(
                self._icon(
                    "dialog-information-symbolic",
                    16,
                )
            )
            note.append(
                self._label(
                    (
                        "PowerDeck verifies each write and "
                        "rolls back on mismatch."
                    ),
                    "powerdeck-quiet-text",
                    wrap=True,
                )
            )
            page.append(note)
            return self._scrolled_page(page)

        def _thermal_page(
            self,
            snapshot: DiscoverySnapshot,
        ) -> Any:
            status = snapshot.status
            capabilities = snapshot.capabilities

            page = self._page(
                "Thermal",
                (
                    "Apply a kernel platform profile "
                    "through powerdeckd."
                ),
            )

            thermal_value = (
                "Unknown"
                if status.thermal.current_profile is None
                else status.thermal.current_profile.value
            )
            profile_value = (
                status.power_manager.current_profile
                or "Unknown"
            )
            governor_value = (
                capabilities.cpu.current_governor
                or "Unknown"
            )

            current_card = self._card(
                (
                    self._row(
                        "Current thermal mode",
                        suffix=self._value_suffix(
                            thermal_value
                        ),
                    ),
                    self._row(
                        "OS power profile",
                        suffix=self._value_suffix(
                            profile_value
                        ),
                    ),
                    self._row(
                        "CPU governor",
                        suffix=self._value_suffix(
                            governor_value
                        ),
                    ),
                )
            )
            page.append(
                self._section(
                    "Current state",
                    current_card,
                )
            )

            modes = [
                profile.value
                for profile
                in capabilities.thermal.supported_profiles
            ]
            current = (
                status.thermal.current_profile.value
                if status.thermal.current_profile
                is not None
                else ""
            )

            controls = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=8,
            )
            dropdown = Gtk.DropDown.new_from_strings(modes)
            dropdown.set_size_request(170, -1)
            if current in modes:
                dropdown.set_selected(
                    modes.index(current)
                )
            controls.append(dropdown)
            controls.append(
                self._button(
                    "Apply",
                    lambda: self._apply_thermal(
                        dropdown
                    ),
                )
            )

            profile_card = self._card(
                (
                    self._row(
                        "Thermal mode",
                        subtitle=(
                            "Choose the laptop thermal "
                            "management profile."
                        ),
                        suffix=controls,
                    ),
                )
            )
            page.append(
                self._section(
                    "Profile",
                    profile_card,
                )
            )
            return self._scrolled_page(page)

        def _switch(
            self,
            key: str,
            active: bool,
        ) -> Any:
            widget = Gtk.Switch(
                active=active,
                valign=Gtk.Align.CENTER,
            )
            self.widgets[key] = widget
            return widget

        def _spin(
            self,
            key: str,
            value: float,
            minimum: float,
            maximum: float,
            step: float,
        ) -> Any:
            widget = Gtk.SpinButton.new_with_range(
                minimum,
                maximum,
                step,
            )
            widget.set_value(value)
            self.widgets[key] = widget
            return widget

        def _combo(
            self,
            key: str,
            values: list[str],
            selected: str,
        ) -> Any:
            widget = Gtk.DropDown.new_from_strings(values)
            if selected in values:
                widget.set_selected(
                    values.index(selected)
                )
            self.widgets[key] = widget
            return widget

        def _saver_page(self) -> Any:
            settings = load_settings()
            runtime_state = SessionController().status()
            active_now = bool(
                runtime_state.get("active")
            )

            page = self._page(
                "Battery Saver",
                (
                    "Turn Battery Saver on or off directly, "
                    "or configure optional automation."
                ),
            )

            active_switch = self._switch(
                "active_now",
                active_now,
            )
            activation = (
                str(runtime_state.get("activation"))
                if active_now
                else "inactive"
            )
            activation_badge = self._label(
                activation,
                "powerdeck-badge",
                xalign=1.0,
            )

            runtime_card = self._card(
                (
                    self._row(
                        "Battery Saver",
                        subtitle=(
                            "Immediate control on AC or "
                            "battery power."
                        ),
                        suffix=active_switch,
                        tall=True,
                    ),
                    self._row(
                        "Activation source",
                        subtitle=(
                            "Shows how the current session "
                            "was activated."
                        ),
                        suffix=activation_badge,
                    ),
                )
            )
            page.append(
                self._section(
                    "Runtime",
                    runtime_card,
                )
            )

            automation_card = self._card(
                (
                    self._row(
                        "Enable automatic Battery Saver",
                        subtitle=(
                            "Allow the user service to react "
                            "to AC transitions."
                        ),
                        suffix=self._switch(
                            "enabled",
                            settings.enabled,
                        ),
                    ),
                    self._row(
                        "Turn on automatically when unplugged",
                        subtitle=(
                            "Activate Battery Saver when "
                            "battery power begins."
                        ),
                        suffix=self._switch(
                            "auto",
                            settings.auto_enable_on_battery,
                        ),
                    ),
                    self._row(
                        "Restore automatically when AC reconnects",
                        subtitle=(
                            "Restore values still owned by "
                            "PowerDeck."
                        ),
                        suffix=self._switch(
                            "restore",
                            settings.restore_on_ac,
                        ),
                    ),
                )
            )
            page.append(
                self._section(
                    "Automation",
                    automation_card,
                )
            )

            display_card = self._card(
                (
                    self._row(
                        "Brightness cap (%)",
                        subtitle=(
                            "Limit maximum screen brightness."
                        ),
                        suffix=self._spin(
                            "brightness",
                            settings.brightness_cap_percent,
                            1,
                            100,
                            1,
                        ),
                    ),
                    self._row(
                        "Only lower brightness",
                        subtitle=(
                            "Never raise brightness above "
                            "the current level."
                        ),
                        suffix=self._switch(
                            "only_lower",
                            settings.only_lower_brightness,
                        ),
                    ),
                    self._row(
                        "Target refresh rate (Hz)",
                        subtitle=(
                            "Choose the internal display "
                            "refresh target."
                        ),
                        suffix=self._spin(
                            "refresh",
                            settings.target_refresh_rate_hz,
                            30,
                            240,
                            1,
                        ),
                    ),
                )
            )
            display_section = self._section(
                "Display",
                display_card,
            )
            display_section.set_hexpand(True)

            performance_card = self._card(
                (
                    self._row(
                        "OS power profile",
                        subtitle=(
                            "Select the operating system "
                            "power profile."
                        ),
                        suffix=self._combo(
                            "power_profile",
                            [
                                "power-saver",
                                "balanced",
                                "performance",
                            ],
                            settings.power_profile,
                        ),
                    ),
                    self._row(
                        "Thermal profile",
                        subtitle=(
                            "Select the thermal management "
                            "profile."
                        ),
                        suffix=self._combo(
                            "saver_thermal",
                            [
                                "quiet",
                                "cool",
                                "balanced",
                                "performance",
                            ],
                            settings.thermal_profile,
                        ),
                    ),
                    self._row(
                        "Disable CPU turbo",
                        subtitle=(
                            "Prevent turbo boost while "
                            "Battery Saver is active."
                        ),
                        suffix=self._switch(
                            "turbo",
                            settings.disable_turbo,
                        ),
                    ),
                    self._row(
                        "Maximum CPU performance (%)",
                        subtitle=(
                            "Limit Intel P-state maximum "
                            "performance."
                        ),
                        suffix=self._spin(
                            "cpu_cap",
                            settings.max_performance_percent,
                            1,
                            100,
                            1,
                        ),
                    ),
                )
            )
            performance_section = self._section(
                "Performance",
                performance_card,
            )
            performance_section.set_hexpand(True)

            columns = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=16,
            )
            columns.add_css_class("powerdeck-two-column")
            columns.set_homogeneous(True)
            columns.append(display_section)
            columns.append(performance_section)
            page.append(columns)

            devices_card = self._card(
                (
                    self._row(
                        "Keyboard backlight level",
                        subtitle=(
                            "Set the keyboard backlight "
                            "brightness."
                        ),
                        suffix=self._spin(
                            "keyboard",
                            settings.keyboard_backlight_level,
                            0,
                            2,
                            1,
                        ),
                    ),
                    self._row(
                        "Mute audio output",
                        subtitle=(
                            "Mute the default output while "
                            "Battery Saver is active."
                        ),
                        suffix=self._switch(
                            "mute",
                            settings.mute_audio,
                        ),
                    ),
                )
            )
            page.append(
                self._section(
                    "Devices",
                    devices_card,
                )
            )

            settings_controls = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=8,
            )
            settings_controls.append(
                self._button(
                    "Save settings",
                    self._save_saver_settings,
                )
            )
            settings_card = self._card(
                (
                    self._row(
                        "Battery Saver settings",
                        subtitle=(
                            "Save values used by the runtime "
                            "switch and automation."
                        ),
                        suffix=settings_controls,
                    ),
                )
            )
            page.append(
                self._section(
                    "Settings",
                    settings_card,
                )
            )

            active_switch.connect(
                "notify::active",
                self._on_saver_active_changed,
            )
            return self._scrolled_page(page)

        def _settings_from_widgets(
            self,
        ) -> SaverSettings:
            return SaverSettings(
                enabled=bool(
                    self.widgets["enabled"].get_active()
                ),
                auto_enable_on_battery=bool(
                    self.widgets["auto"].get_active()
                ),
                restore_on_ac=bool(
                    self.widgets["restore"].get_active()
                ),
                brightness_cap_percent=int(
                    self.widgets[
                        "brightness"
                    ].get_value()
                ),
                only_lower_brightness=bool(
                    self.widgets[
                        "only_lower"
                    ].get_active()
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

        def _on_saver_active_changed(
            self,
            switch: Any,
            _parameter: Any,
        ) -> None:
            desired = bool(switch.get_active())
            current = bool(
                SessionController().status().get(
                    "active"
                )
            )
            if desired == current:
                return

            settings = self._settings_from_widgets()
            save_settings(settings)

            if desired:
                self._run_operation(
                    "Turning Battery Saver on...",
                    lambda: SessionController().apply_now(
                        settings,
                        activation="manual",
                    ),
                )
            else:
                self._run_operation(
                    "Turning Battery Saver off...",
                    lambda: SessionController().restore_now(),
                )

        def _save_saver_settings(self) -> None:
            settings = self._settings_from_widgets()
            save_settings(settings)
            self._toast(
                "Battery Saver settings saved."
            )

        def _apply_thermal(
            self,
            dropdown: Any,
        ) -> None:
            profile = _selected_text(dropdown)
            self._run_operation(
                f"Applying thermal mode {profile}...",
                lambda: asyncio.run(
                    _client_call(
                        "set_thermal_profile",
                        profile,
                    )
                ),
            )

        def _apply_charge_mode(
            self,
            dropdown: Any,
        ) -> None:
            mode = _selected_text(dropdown)
            self._run_operation(
                f"Applying charging mode {mode}...",
                lambda: asyncio.run(
                    _client_call(
                        "set_charge_mode",
                        mode,
                    )
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
                (
                    "Applying custom charging "
                    "thresholds..."
                ),
                lambda: asyncio.run(
                    _client_call(
                        "set_charge_thresholds",
                        start_value,
                        end_value,
                    )
                ),
            )

        def _header_status(
            self,
            snapshot: DiscoverySnapshot,
        ) -> Any:
            status = snapshot.status
            battery = (
                status.batteries[0]
                if status.batteries
                else None
            )

            summary = (
                "Battery unavailable"
                if battery is None
                else (
                    f"{battery.capacity_percent}%"
                    " · "
                    + (
                        "AC"
                        if status.on_ac_power
                        else "Battery"
                    )
                )
            )

            chip = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=6,
            )
            chip.add_css_class(
                "powerdeck-status-chip"
            )
            chip.append(
                self._icon(
                    "battery-symbolic",
                    15,
                )
            )
            chip.append(
                self._label(
                    summary,
                    "powerdeck-value",
                )
            )
            return chip

        def _brand(self) -> Any:
            brand = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=8,
            )
            brand.append(
                self._icon(
                    "power-profile-performance-symbolic",
                    19,
                )
            )
            brand.append(
                self._label(
                    "PowerDeck",
                    "powerdeck-brand",
                )
            )
            return brand

        def _navigation_button(
            self,
            key: str,
            title: str,
            icon_name: str,
            group: Any | None,
        ) -> Any:
            button = Gtk.ToggleButton()
            button.add_css_class("powerdeck-nav")
            if group is not None:
                button.set_group(group)

            content = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=11,
            )
            content.append(
                self._icon(
                    icon_name,
                    18,
                )
            )
            content.append(
                self._label(
                    title,
                    "powerdeck-row-title",
                )
            )
            button.set_child(content)
            button.connect(
                "toggled",
                self._on_navigation_toggled,
                key,
            )
            return button

        def _on_navigation_toggled(
            self,
            button: Any,
            key: str,
        ) -> None:
            if (
                button.get_active()
                and self.stack is not None
            ):
                self.stack.set_visible_child_name(key)

        def _sidebar(self) -> Any:
            sidebar = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=6,
            )
            sidebar.add_css_class(
                "powerdeck-sidebar"
            )
            sidebar.set_size_request(210, -1)

            first: Any = None
            for item in NAVIGATION:
                button = self._navigation_button(
                    item.key,
                    item.title,
                    item.icon_name,
                    first,
                )
                if first is None:
                    first = button
                sidebar.append(button)

            spacer = Gtk.Box()
            spacer.set_vexpand(True)
            sidebar.append(spacer)

            version = self._label(
                "v0.1 candidate",
                "powerdeck-row-subtitle",
            )
            version.set_margin_start(12)
            version.set_margin_bottom(8)
            sidebar.append(version)

            if first is not None:
                first.set_active(True)
            return sidebar

        def _render(
            self,
            snapshot: DiscoverySnapshot,
        ) -> bool:
            self.busy = False
            self.snapshot = snapshot
            self.widgets.clear()

            stack = Gtk.Stack()
            stack.set_hexpand(True)
            stack.set_vexpand(True)
            stack.set_transition_type(
                Gtk.StackTransitionType.NONE
            )
            stack.add_named(
                self._battery_page(snapshot),
                "battery",
            )
            stack.add_named(
                self._thermal_page(snapshot),
                "thermal",
            )
            stack.add_named(
                self._saver_page(),
                "saver",
            )
            self.stack = stack

            body = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=0,
            )
            body.add_css_class("powerdeck-root")
            body.append(self._sidebar())
            body.append(stack)

            refresh = Gtk.Button(
                icon_name="view-refresh-symbolic",
                tooltip_text="Refresh hardware state",
            )
            refresh.connect(
                "clicked",
                lambda _button: self._refresh(),
            )

            header = Adw.HeaderBar()
            header.set_title_widget(Gtk.Box())
            header.pack_start(self._brand())
            header.pack_end(refresh)
            header.pack_end(
                self._header_status(snapshot)
            )

            toolbar = Adw.ToolbarView()
            toolbar.add_top_bar(header)
            toolbar.set_content(body)

            overlay = Adw.ToastOverlay()
            overlay.set_child(toolbar)
            self.overlay = overlay
            self._set_content(overlay)
            return False

    app = PowerDeckApplication()
    return int(
        app.run(
            list(
                sys.argv
                if argv is None
                else argv
            )
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
