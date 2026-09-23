from unittest.mock import Mock

import pytest
from app.actions.executor import ActionExecutor
from app.actions.schema import Action, ActionType
from app.brain.jev import JevDecisionEngine
from app.brain.mock import MockDecisionEngine


def test_open_app_action_requires_target():
    with pytest.raises(ValueError):
        Action(action=ActionType.OPEN_APP)


def test_dry_run_never_calls_macos():
    macos = Mock()
    result = ActionExecutor(macos).execute(Action(action=ActionType.OPEN_APP, target="Google Chrome"), dry_run=True)
    assert result == "DRY RUN - nothing executed"
    macos.execute_open_app.assert_not_called()


def test_mock_decision_engine_is_replaceable():
    action = Action(action=ActionType.OPEN_APP, target="Google Chrome")
    assert MockDecisionEngine(action).decide("open Chrome") == action


def test_jev_selects_only_an_offered_app():
    response = {"answers": {"action": {"choice": "OPEN_APP"}, "target": {"choice": "Google Chrome"}}}
    action = JevDecisionEngine._parse_response(response, "open Chrome", ["Google Chrome"])
    assert action == Action(action="OPEN_APP", target="Google Chrome")


def test_jev_rejects_unoffered_app():
    response = {"answers": {"action": {"choice": "OPEN_APP"}, "target": {"choice": "Terminal"}}}
    with pytest.raises(ValueError, match="not offered"):
        JevDecisionEngine._parse_response(response, "open Terminal", ["Google Chrome"])
