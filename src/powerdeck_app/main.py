"""GTK4/Libadwaita standalone application entry point."""

from __future__ import annotations

import sys
import threading
from collections.abc import Sequence
from importlib import import_module
from typing import Any

from powerdeck_app.view_model import DashboardModel, PageModel, build_dashboard
from powerdeck_backends.scanner import PowerDeckScanner

_APPLICATION_ID = "org.powerdeck.PowerDeck"


def _load_gi() -> tuple[Any, Any, Any, Any]:
    gi = import_module("gi")
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")

    gtk = import_module("gi.repository.Gtk")
    adw = import_module("gi.repository.Adw")
    gio = import_module("gi.repository.Gio")
    glib = import_module("gi.repository.GLib")
    return gtk, adw, gio, glib


def _dependency_error(error: BaseException) -> str:
    return (
        "PowerDeck needs the system GTK bindings.\n"
        "On CachyOS/Arch install: python-gobject gtk4 libadwaita\n"
        f"Import error: {error}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        Gtk, Adw, Gio, GLib = _load_gi()
    except (ImportError, ValueError) as error:
        print(_dependency_error(error), file=sys.stderr)
        return 1

    class PowerDeckApplication(Adw.Application):  # type: ignore[name-defined]
        def __init__(self) -> None:
            super().__init__(
                application_id=_APPLICATION_ID,
                flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
            )
            self.window: Any = None
            self.scanning = False

        def do_activate(self) -> None:
            if self.window is None:
                self.window = Adw.ApplicationWindow(application=self)
                self.window.set_title("PowerDeck")
                self.window.set_default_size(860, 640)
                self.window.set_size_request(480, 420)
                self._show_loading()
                self._refresh()
            self.window.present()

        def _show_loading(self) -> None:
            box = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=16,
                halign=Gtk.Align.CENTER,
                valign=Gtk.Align.CENTER,
            )
            spinner = Gtk.Spinner(spinning=True)
            title = Gtk.Label(label="Scanning this laptop…")
            title.add_css_class("title-2")
            description = Gtk.Label(
                label=(
                    "PowerDeck is reading battery, thermal, display, "
                    "and session state."
                )
            )
            description.set_wrap(True)
            description.set_justify(Gtk.Justification.CENTER)
            box.append(spinner)
            box.append(title)
            box.append(description)
            self.window.set_content(box)

        def _show_error(self, message: str) -> None:
            page = Adw.StatusPage()
            page.set_icon_name("dialog-error-symbolic")
            page.set_title("PowerDeck could not scan the system")
            page.set_description(message)
            retry = Gtk.Button(label="Try Again")
            retry.add_css_class("suggested-action")
            retry.connect("clicked", lambda _button: self._refresh())
            page.set_child(retry)
            self.window.set_content(page)

        def _refresh(self) -> None:
            if self.scanning:
                return
            self.scanning = True
            self._show_loading()

            def worker() -> None:
                try:
                    snapshot = PowerDeckScanner().scan()
                    dashboard = build_dashboard(snapshot)
                except Exception as error:
                    GLib.idle_add(
                        self._finish_error,
                        f"{type(error).__name__}: {error}",
                    )
                    return
                GLib.idle_add(self._finish_refresh, dashboard)

            threading.Thread(
                target=worker,
                name="powerdeck-scan",
                daemon=True,
            ).start()

        def _finish_error(self, message: str) -> bool:
            self.scanning = False
            self._show_error(message)
            return False

        def _finish_refresh(
            self,
            dashboard: DashboardModel,
        ) -> bool:
            self.scanning = False
            self._render_dashboard(dashboard)
            return False

        def _render_dashboard(
            self,
            dashboard: DashboardModel,
        ) -> None:
            stack = Adw.ViewStack()
            stack.set_vexpand(True)

            for page_model in (
                dashboard.battery,
                dashboard.thermal,
                dashboard.saver,
            ):
                page = self._build_page(page_model)
                stack.add_titled(
                    page,
                    page_model.name,
                    page_model.title,
                )

            if dashboard.diagnostics:
                diagnostics = PageModel(
                    name="diagnostics",
                    title="Diagnostics",
                    description="Issues reported by the capability scanner.",
                    groups=(
                        (
                            "Current issues",
                            tuple(
                                self._diagnostic_row(item)
                                for item in dashboard.diagnostics
                            ),
                        ),
                    ),
                )
                stack.add_titled(
                    self._build_page(diagnostics),
                    diagnostics.name,
                    diagnostics.title,
                )

            switcher_title = Adw.ViewSwitcherTitle()
            switcher_title.set_stack(stack)

            refresh = Gtk.Button(
                icon_name="view-refresh-symbolic",
                tooltip_text="Refresh hardware state",
            )
            refresh.connect(
                "clicked",
                lambda _button: self._refresh(),
            )

            header = Adw.HeaderBar()
            header.set_title_widget(switcher_title)
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
            self.window.set_content(toolbar)

        @staticmethod
        def _diagnostic_row(message: str) -> Any:
            from powerdeck_app.view_model import RowModel

            severity, separator, text = message.partition(": ")
            return RowModel(
                severity.title() if separator else "Issue",
                text if separator else message,
            )

        @staticmethod
        def _build_page(page_model: PageModel) -> Any:
            page = Adw.PreferencesPage()
            page.set_title(page_model.title)
            page.set_description(page_model.description)

            for group_title, rows in page_model.groups:
                group = Adw.PreferencesGroup()
                group.set_title(group_title)

                for item in rows:
                    row = Adw.ActionRow()
                    row.set_title(item.label)
                    if item.description is not None:
                        row.set_subtitle(item.description)

                    value = Gtk.Label(
                        label=item.value,
                        xalign=1.0,
                        valign=Gtk.Align.CENTER,
                        selectable=True,
                    )
                    value.set_wrap(True)
                    value.set_max_width_chars(42)
                    value.add_css_class("dim-label")
                    row.add_suffix(value)
                    group.add(row)

                page.add(group)

            return page

    app = PowerDeckApplication()
    arguments = list(sys.argv if argv is None else argv)
    return int(app.run(arguments))


if __name__ == "__main__":
    raise SystemExit(main())
