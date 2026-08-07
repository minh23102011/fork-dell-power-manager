from pathlib import Path

from powerdeck_app.theme import POWERDECK_CSS


def test_theme_is_flat_and_has_no_blur_or_gradients() -> None:
    css = POWERDECK_CSS.lower()

    assert "blur(" not in css
    assert "backdrop-filter" not in css
    assert "linear-gradient" not in css
    assert "radial-gradient" not in css
    assert "box-shadow" not in css


def test_app_uses_single_retained_stack_without_view_switcher_bar() -> None:
    root = Path(__file__).resolve().parents[2]
    main = (
        root / "src" / "powerdeck_app" / "main.py"
    ).read_text(encoding="utf-8")

    assert "Gtk.StackTransitionType.NONE" in main
    assert "Adw.ViewSwitcherBar" not in main
    assert "Adw.PreferencesPage" not in main
    assert "powerdeck-sidebar" in main
