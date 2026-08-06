from powerdeck_agent.session import select_automatic_action
from powerdeck_agent.settings import SaverSettings


def test_manual_off_on_battery_is_not_immediately_reapplied() -> None:
    settings = SaverSettings(enabled=True, auto_enable_on_battery=True)
    state = {"active": False, "activation": None, "last_on_ac": False}
    assert select_automatic_action(settings, state, on_ac=False) is None


def test_unplug_transition_applies_automatic_saver() -> None:
    settings = SaverSettings(enabled=True, auto_enable_on_battery=True)
    state = {"active": False, "activation": None, "last_on_ac": True}
    assert select_automatic_action(settings, state, on_ac=False) == "apply"


def test_manual_session_is_not_restored_on_ac() -> None:
    settings = SaverSettings(restore_on_ac=True)
    state = {"active": True, "activation": "manual", "last_on_ac": False}
    assert select_automatic_action(settings, state, on_ac=True) is None


def test_automatic_session_is_restored_on_ac() -> None:
    settings = SaverSettings(restore_on_ac=True)
    state = {"active": True, "activation": "automatic", "last_on_ac": False}
    assert select_automatic_action(settings, state, on_ac=True) == "restore"


def test_unknown_ac_state_never_changes_runtime() -> None:
    settings = SaverSettings()
    state = {"active": False}
    assert select_automatic_action(settings, state, on_ac=None) is None
