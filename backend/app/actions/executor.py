from __future__ import annotations

from app.actions.macos import MacOSExecutor
from app.actions.registry import COMMAND_REGISTRY
from app.actions.schema import Action


class ActionExecutor:
    def __init__(self, macos: MacOSExecutor) -> None:
        self.macos = macos

    def execute(self, action: Action, dry_run: bool = False) -> str:
        if dry_run:
            return "DRY RUN - nothing executed"
        handler = COMMAND_REGISTRY.get(action.action)
        if handler is None:
            raise ValueError(f"No executor registered for {action.action}")
        return handler(self.macos, action)
