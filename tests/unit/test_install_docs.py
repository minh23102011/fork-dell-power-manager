from pathlib import Path


def test_install_docs_list_required_system_dependencies() -> None:
    root = Path(__file__).resolve().parents[2]
    readme = (root / "README.md").read_text(encoding="utf-8")
    html = (root / "README.html").read_text(encoding="utf-8")

    required = (
        "python-dbus-next",
        "python-gobject",
        "gtk4",
        "libadwaita",
        "polkit",
        "brightnessctl",
        "power-profiles-daemon",
    )

    for dependency in required:
        assert dependency in readme
        assert dependency in html


def test_installer_uses_dependency_checker_and_marks_optional_tools() -> None:
    root = Path(__file__).resolve().parents[2]
    installer = (
        root / "scripts" / "install-local-v0.1.sh"
    ).read_text(encoding="utf-8")
    checker = (
        root / "scripts" / "check-dependencies.sh"
    ).read_text(encoding="utf-8")

    assert "check-dependencies.sh" in installer
    assert "wireplumber" in installer
    assert "niri" in installer
    assert "--required-only" in installer
    assert "Python GTK/D-Bus runtime" in checker
