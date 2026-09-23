from __future__ import annotations

import re
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
        apps = context.installed_apps or [
            "Google Chrome", "Safari", "Visual Studio Code", "Notes", "Finder", "System Settings",
        ]
        candidates = self._candidates(transcript)
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
                "value": {"type": "choice", "instructions": "Choose the exact argument value from these code-owned candidates.", "criteria": candidates},
                "engine": {"type": "choice", "criteria": {"google": "Google", "youtube": "YouTube"}},
                "key": {"type": "choice", "criteria": {key: key for key in ("ENTER", "ESCAPE", "TAB", "SPACE", "BACKSPACE", "DELETE", "UP", "DOWN", "LEFT", "RIGHT")}},
                "direction": {"type": "choice", "criteria": {direction: direction for direction in ("UP", "DOWN", "TOP", "BOTTOM")}},
                "amount": {"type": "choice", "criteria": {str(amount): str(amount) for amount in range(1, 21)}},
                "seconds": {"type": "choice", "criteria": {str(seconds): str(seconds) for seconds in (1, 2, 5, 10)}},
            },
        }
        response = self.client.post(config.TYPESAFE_URL, json=payload, headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        response.raise_for_status()
        return self._parse_response(response.json(), transcript, apps, candidates)

    @staticmethod
    def _candidates(transcript: str) -> dict[str, str]:
        values = [transcript.strip()]
        patterns = [
            r"(?:type|write|enter|input)\s+(.+)$",
            r"(?:search|google|look up|find)(?:\s+\w+)?\s+(?:for\s+)?(.+)$",
            r"(?:go to|open)\s+(.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, transcript, re.IGNORECASE)
            if match:
                values.append(match.group(1).strip().rstrip("."))
        return {f"value_{index}": value for index, value in enumerate(dict.fromkeys(v for v in values if v))}

    @staticmethod
    def _parse_response(data: dict[str, Any], transcript: str, apps: list[str], candidates: dict[str, str] | None = None) -> Action:
        answers = data.get("answers", {})
        action = str(answers.get("action", {}).get("choice", "DONE"))
        if action not in {item.value for item in ActionType}:
            raise ValueError(f"Jev returned unsupported action: {action}")
        target = answers.get("target", {}).get("choice")
        if target == "none":
            target = None
        if action in {ActionType.OPEN_APP.value, ActionType.SWITCH_APP.value} and target not in apps:
            raise ValueError("Jev selected an app that was not offered")
        candidates = candidates or JevDecisionEngine._candidates(transcript)

        def selected(name: str, default: str | None = None) -> str | None:
            choice = answers.get(name, answers.get("value", {})).get("choice", default)
            return candidates.get(choice, choice)

        values: dict[str, Any] = {"action": action}
        if action in {ActionType.OPEN_APP.value, ActionType.SWITCH_APP.value}:
            values["target"] = target
        elif action == ActionType.OPEN_URL.value:
            url = selected("url", selected("value", "")) or ""
            known_sites = {"youtube": "https://www.youtube.com", "leetcode": "https://leetcode.com", "google": "https://www.google.com"}
            values["url"] = known_sites.get(url.lower(), url if url.startswith(("http://", "https://")) else f"https://{url}")
        elif action == ActionType.SEARCH_WEB.value:
            values["query"] = selected("query", selected("value", transcript))
            values["engine"] = selected("engine", "google")
        elif action == ActionType.TYPE_TEXT.value:
            values["text"] = selected("text", selected("value", transcript))
        elif action == ActionType.PRESS_KEY.value:
            values["key"] = str(selected("key", "ENTER")).upper()
        elif action == ActionType.SCROLL.value:
            values["direction"] = str(selected("direction", "DOWN")).upper()
            values["amount"] = int(selected("amount", "5") or 5)
        elif action == ActionType.WAIT.value:
            values["seconds"] = float(selected("seconds", "1") or 1)
        return action_from_dict(values)
