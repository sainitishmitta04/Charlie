from unittest.mock import Mock

import pytest
from app.actions.executor import ActionExecutor
from app.actions.schema import Action, ActionType
from app.brain.jev import JevDecisionEngine
from app.brain.mock import MockDecisionEngine

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
        "key": None, "direction": "DOWN", "amount": 5, "engine": None, "seconds": None,
    }


def test_jev_rejects_unoffered_app():
    response = {"answers": {"action": {"choice": "OPEN_APP"}, "target": {"choice": "Terminal"}}}
    with pytest.raises(ValueError, match="not offered"):
        JevDecisionEngine._parse_response(response, "open Terminal", ["Google Chrome"])
