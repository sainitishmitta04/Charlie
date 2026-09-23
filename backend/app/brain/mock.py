from __future__ import annotations

from app.actions.schema import Action, DecisionContext


class MockDecisionEngine:
    def __init__(self, action: Action) -> None:
        self.action = action

    def decide(self, transcript: str, context: DecisionContext | None = None) -> Action:
        return self.action
