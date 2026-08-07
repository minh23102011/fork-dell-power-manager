from pathlib import Path


def test_readme_demo_assets_exist() -> None:
    root = Path(__file__).resolve().parents[2]

    assert (root / "README.html").is_file()
    assert (root / "README.css").is_file()
    assert (root / "README.js").is_file()
    assert (
        root
        / "docs"
        / "assets"
        / "powerdeck-ui.png"
    ).is_file()


def test_html_demo_is_marked_as_simulation() -> None:
    root = Path(__file__).resolve().parents[2]
    html = (root / "README.html").read_text(encoding="utf-8")

    assert "SIMULATION" in html
    assert "cannot access or change your hardware" in html
