from __future__ import annotations

from app.actions.macos import MacOSExecutor
from app.actions.schema import Action, ActionType


class ActionExecutor:
    def __init__(self, macos: MacOSExecutor) -> None:
        self.macos = macos

    def execute(self, action: Action, dry_run: bool = False) -> str:
        if dry_run:
            return "DRY RUN - nothing executed"
        if action.action == ActionType.OPEN_APP:
            return self.macos.execute_open_app(action.target or "")
        raise ValueError(f"No executor registered for {action.action}")
