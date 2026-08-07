from powerdeck_app.ui_spec import NAVIGATION


def test_navigation_has_only_real_v01_pages() -> None:
    assert tuple(item.key for item in NAVIGATION) == (
        "battery",
        "thermal",
        "saver",
    )


def test_navigation_titles_are_direct() -> None:
    assert tuple(item.title for item in NAVIGATION) == (
        "Battery",
        "Thermal",
        "Battery Saver",
    )
