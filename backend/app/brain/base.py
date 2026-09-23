from __future__ import annotations

from typing import Protocol

from app.actions.schema import Action, DecisionContext


class DecisionEngine(Protocol):
    def decide(self, transcript: str, context: DecisionContext | None = None) -> Action:
        """Turn speech text into one validated, executable action."""
