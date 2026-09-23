from __future__ import annotations

from app.actions.schema import Action, DecisionContext


class LayaDecisionEngine:
    """Reserved adapter boundary for a future Laya implementation."""

    def decide(self, transcript: str, context: DecisionContext | None = None) -> Action:
        raise NotImplementedError("LayaDecisionEngine is not implemented yet")