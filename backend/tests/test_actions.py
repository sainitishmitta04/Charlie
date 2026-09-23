from unittest.mock import Mock

import pytest
from app.actions.executor import ActionExecutor
from app.actions.macos import installed_applications
from app.actions.schema import Action, ActionType
from app.brain.jev import JevDecisionEngine
from app.brain.mock import MockDecisionEngine
from app.commands.compound import split_compound

VALID_ACTIONS = [
    Action(action=ActionType.OPEN_APP, target="Google Chrome"),
    Action(action=ActionType.OPEN_URL, url="https://www.youtube.com"),
    Action(action=ActionType.SEARCH_WEB, query="Python tutorials", engine="google"),
    Action(action=ActionType.TYPE_TEXT, text="hello world"),
    Action(action=ActionType.PRESS_KEY, key="ENTER"),
    Action(action=ActionType.SCROLL, direction="DOWN", amount=5),
    Action(action=ActionType.VOLUME_UP),
    Action(action=ActionType.VOLUME_DOWN),
    Action(action=ActionType.MUTE),
    Action(action=ActionType.SCREENSHOT),
    Action(action=ActionType.LOCK_SCREEN),
    Action(action=ActionType.DARK_MODE_ON),
    Action(action=ActionType.DARK_MODE_OFF),
    Action(action=ActionType.SYSTEM_SETTINGS, setting="ACCESSIBILITY"),
    Action(action=ActionType.SWITCH_APP, target="Google Chrome"),
    Action(action=ActionType.WAIT, seconds=1),
]


def test_every_phase_2_action_is_dry_run_safe():
    macos = Mock()
    executor = ActionExecutor(macos)
    for action in VALID_ACTIONS:
        assert executor.execute(action, dry_run=True) == "DRY RUN - nothing executed"
    macos.execute.assert_not_called()


@pytest.mark.parametrize("action", VALID_ACTIONS)
def test_every_phase_2_action_dispatches_through_macos_registry(action):
    macos = Mock()
    macos.execute.return_value = "ok"
    assert ActionExecutor(macos).execute(action) == "ok"
    macos.execute.assert_called_once_with(action.action.value, action)


def test_open_app_action_requires_target():
    with pytest.raises(ValueError):
        Action(action=ActionType.OPEN_APP)


def test_action_arguments_are_rejected_when_invalid():
    with pytest.raises(ValueError, match="direction"):
        Action(action=ActionType.SCROLL, direction="SIDEWAYS", amount=5)
    with pytest.raises(ValueError, match="supported"):
        Action(action=ActionType.PRESS_KEY, key="LAUNCH_TERMINAL")
    with pytest.raises(ValueError, match="http"):
        Action(action=ActionType.OPEN_URL, url="javascript:alert(1)")


def test_mock_decision_engine_is_replaceable():
    action = Action(action=ActionType.OPEN_APP, target="Google Chrome")
    assert MockDecisionEngine(action).decide("open Chrome") == action


def test_jev_selects_only_an_offered_app():
    response = {"answers": {"action": {"choice": "OPEN_APP"}, "target": {"choice": "Google Chrome"}}}
    action = JevDecisionEngine._parse_response(response, "open Chrome", ["Google Chrome"])
    assert action == Action(action="OPEN_APP", target="Google Chrome")


def test_jev_parses_scroll_arguments():
    response = {
        "answers": {
            "action": {"choice": "SCROLL"},
            "direction": {"choice": "DOWN"},
            "amount": {"choice": "5"},
        }
    }
    assert JevDecisionEngine._parse_response(response, "scroll down", []).model_dump() == {
        "action": "SCROLL", "target": None, "url": None, "query": None, "text": None,
        "key": None, "direction": "DOWN", "amount": 5, "engine": None, "setting": None, "seconds": None,
    }


def test_jev_rejects_unoffered_app():
    response = {"answers": {"action": {"choice": "OPEN_APP"}, "target": {"choice": "Terminal"}}}
    with pytest.raises(ValueError, match="not offered"):
        JevDecisionEngine._parse_response(response, "open Terminal", ["Google Chrome"])


def test_system_settings_validation_and_jev_parsing():
    with pytest.raises(ValueError, match="not supported"):
        Action(action=ActionType.SYSTEM_SETTINGS, setting="USERS")
    response = {"answers": {"action": {"choice": "SYSTEM_SETTINGS"}, "setting": {"choice": "WI_FI"}}}
    action = JevDecisionEngine._parse_response(response, "open Wi-Fi settings", [])
    assert action == Action(action=ActionType.SYSTEM_SETTINGS, setting="WI_FI")


@pytest.mark.parametrize(
    ("transcript", "expected"),
    [
        ("open Chrome and go to YouTube", ["open Chrome", "go to YouTube"]),
        ("open Notes and type buy milk", ["open Notes", "type buy milk"]),
        ("type bread and butter", ["type bread and butter"]),
    ],
)
def test_compound_commands_split_only_at_command_boundaries(transcript, expected):
    assert split_compound(transcript) == expected


def test_installed_application_discovery_returns_sorted_unique_names(monkeypatch, tmp_path):
    applications = tmp_path / "Applications"
    applications.mkdir()
    (applications / "Zed.app").mkdir()
    (applications / "Arc.app").mkdir()
    class FakePath:
        def __new__(cls, value):
            return applications if str(value) == "/Applications" else tmp_path / "empty"

        @staticmethod
        def home():
            return applications

    monkeypatch.setattr("app.actions.macos.Path", FakePath)
    installed_applications.cache_clear()
    names = installed_applications()
    assert names == ["Arc", "Finder", "System Settings", "Zed"]
    installed_applications.cache_clear()
