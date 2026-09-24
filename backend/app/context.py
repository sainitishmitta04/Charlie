from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any

from app.actions.schema import Action, ActionType


@dataclass
class TaskState:
    steps: list[str] = field(default_factory=list)
    completed_steps: list[str] = field(default_factory=list)
    status: str = "ACTIVE"

    @classmethod
    def start(cls, actions: list[Action]) -> TaskState:
        return cls([action.action.value for action in actions])

    def complete(self, action: Action) -> None:
        self.completed_steps.append(action.action.value)
        if len(self.completed_steps) >= len(self.steps):
            self.status = "COMPLETED"

    def fail(self) -> None:
        self.status = "FAILED"

    def as_dict(self) -> dict[str, Any]:
        return {"steps": self.steps, "completed_steps": self.completed_steps, "status": self.status}


@dataclass
class SessionContext:
    current_app: str | None = None
    previous_app: str | None = None
    current_url: str | None = None
    last_action: str | None = None
    last_target: str | None = None
    last_text: str | None = None
    document_mode: bool = False
    list_mode: bool = False
    list_number: int = 1
    active_task: TaskState | None = None
    last_activity: float = field(default_factory=monotonic, repr=False)

    def as_dict(self) -> dict[str, Any]:
        data = {
            "current_app": self.current_app,
            "previous_app": self.previous_app,
            "current_url": self.current_url,
            "last_action": self.last_action,
            "last_target": self.last_target,
            "last_text": self.last_text,
        }
        if self.document_mode:
            data["document_mode"] = True
        if self.list_mode:
            data["list_mode"] = True
            data["list_number"] = self.list_number
        if self.active_task is not None:
            data["active_task"] = self.active_task.as_dict()
        return {key: value for key, value in data.items() if value is not None}

    def clear(self) -> None:
        self.current_app = None
        self.previous_app = None
        self.current_url = None
        self.last_action = None
        self.last_target = None
        self.last_text = None
        self.document_mode = False
        self.list_mode = False
        self.list_number = 1
        self.active_task = None
        self.last_activity = monotonic()

    def expired(self, timeout_seconds: float) -> bool:
        return timeout_seconds > 0 and monotonic() - self.last_activity > timeout_seconds

    def update_from_action(self, action: Action) -> None:
        previous_app = self.current_app
        if action.action in {ActionType.OPEN_APP, ActionType.SWITCH_APP}:
            self.previous_app = previous_app if action.target != previous_app else self.previous_app
            self.current_app = action.target
        elif action.action in {ActionType.CLOSE_APP, ActionType.QUIT_APP} and action.target == self.current_app:
            self.previous_app = self.current_app
            self.current_app = None
        elif action.action == ActionType.OPEN_URL:
            self.current_url = action.url
        elif action.action == ActionType.SEARCH_WEB or action.action == ActionType.SEARCH_CURRENT_SITE:
            self.last_target = action.query
        elif action.action == ActionType.PRESS_KEY and action.key in {"ENTER", "RETURN"}:
            self.last_target = action.key
            self.next_list_item()
        elif action.action == ActionType.TYPE_TEXT:
            self.last_text = action.text
            self.last_target = action.text
        elif action.action in {ActionType.ACCESSIBILITY_CLICK, ActionType.ACCESSIBILITY_SELECT, ActionType.ACCESSIBILITY_FOCUS}:
            self.last_target = action.target
        self.last_action = action.action.value
        if action.target is not None and action.action not in {ActionType.OPEN_APP, ActionType.SWITCH_APP}:
            self.last_target = action.target
        if self.active_task is not None:
            self.active_task.complete(action)
        self.last_activity = monotonic()

    def start_numbered_list(self) -> None:
        self.document_mode = True
        self.list_mode = True
        self.list_number = 1
        self.last_activity = monotonic()

    def next_list_item(self) -> None:
        if self.list_mode:
            self.list_number += 1
            self.last_activity = monotonic()

    def start_task(self, actions: list[Action]) -> None:
        self.active_task = TaskState.start(actions)
        self.last_activity = monotonic()

    def fail_task(self) -> None:
        if self.active_task is not None:
            self.active_task.fail()
        self.last_activity = monotonic()
