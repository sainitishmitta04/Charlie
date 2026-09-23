from __future__ import annotations

from typing import Any

import httpx

from app import config
from app.actions.schema import Action, ActionType, DecisionContext, action_from_dict


class JevDecisionEngine:
    """Jev adapter. Jev selects from code-owned action and app candidates."""

    def __init__(self, api_key: str | None = None, model: str | None = None, client: httpx.Client | None = None) -> None:
        self.api_key = api_key or config.TYPESAFE_API_KEY
        if not self.api_key:
            raise ValueError("TYPESAFE_API_KEY is not set; add it to .env")
        self.model = model or config.JEV_MODEL
        self.client = client or httpx.Client(timeout=20.0)

    def decide(self, transcript: str, context: DecisionContext | None = None) -> Action:
        context = context or DecisionContext(transcript=transcript)
        apps = context.installed_apps or ["Google Chrome", "Safari", "Notes", "Finder", "System Settings"]
        payload = {
            "model": self.model,
            "state": {"transcript": transcript, "frontmost_app": context.frontmost_app or "", "installed_apps": apps},
            "questions": {
                "action": {
                    "type": "choice",
                    "instructions": "Choose the single computer action requested by the transcript.",
                    "criteria": {item.value: item.value.replace("_", " ").lower() for item in ActionType},
                },
                "target": {
                    "type": "choice",
                    "instructions": "If the action is OPEN_APP or SWITCH_APP, choose the matching installed app. Otherwise choose none.",
                    "criteria": {**{app: app for app in apps}, "none": "No app target is needed"},
                },
            },
        }
        response = self.client.post(config.TYPESAFE_URL, json=payload, headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        response.raise_for_status()
        return self._parse_response(response.json(), transcript, apps)

    @staticmethod
    def _parse_response(data: dict[str, Any], transcript: str, apps: list[str]) -> Action:
        answers = data.get("answers", {})
        action = str(answers.get("action", {}).get("choice", "DONE"))
        if action not in {item.value for item in ActionType}:
            raise ValueError(f"Jev returned unsupported action: {action}")
        target = answers.get("target", {}).get("choice")
        if target == "none":
            target = None
        if action in {ActionType.OPEN_APP.value, ActionType.SWITCH_APP.value} and target not in apps:
            raise ValueError("Jev selected an app that was not offered")
        if action == ActionType.OPEN_APP.value:
            return action_from_dict({"action": action, "target": target})
        raise ValueError(f"Action {action} is not implemented in the MVP executor")
