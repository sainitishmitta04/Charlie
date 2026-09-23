from __future__ import annotations

from collections.abc import Callable

from app.actions.macos import MacOSExecutor
from app.actions.schema import Action, ActionType

ActionHandler = Callable[[MacOSExecutor, Action], str]


def _macos_handler(action_name: str) -> ActionHandler:
    return lambda macos, action: macos.execute(action_name, action)


COMMAND_REGISTRY: dict[ActionType, ActionHandler] = {
    action_type: _macos_handler(action_type.value)
    for action_type in ActionType
}