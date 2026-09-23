from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ActionType(StrEnum):
    OPEN_APP = "OPEN_APP"
    OPEN_URL = "OPEN_URL"
    SEARCH_WEB = "SEARCH_WEB"
    TYPE_TEXT = "TYPE_TEXT"
    PRESS_KEY = "PRESS_KEY"
    SCROLL = "SCROLL"
    VOLUME = "VOLUME"
    MEDIA = "MEDIA"
    SCREENSHOT = "SCREENSHOT"
    LOCK_SCREEN = "LOCK_SCREEN"
    SYSTEM_SETTING = "SYSTEM_SETTING"
    ACCESSIBILITY_SETTING = "ACCESSIBILITY_SETTING"
    SWITCH_APP = "SWITCH_APP"
    WAIT = "WAIT"
    DONE = "DONE"


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ActionType
    target: str | None = Field(default=None, min_length=1)
    url: str | None = None
    query: str | None = None
    text: str | None = None
    key: str | None = None
    direction: str | None = None
    amount: int | None = Field(default=None, ge=1, le=20)
    operation: str | None = None
    setting: str | None = None
    seconds: float | None = Field(default=None, ge=0, le=60)

    @model_validator(mode="after")
    def validate_arguments(self) -> Action:
        required: dict[ActionType, tuple[str, ...]] = {
            ActionType.OPEN_APP: ("target",),
            ActionType.OPEN_URL: ("url",),
            ActionType.SEARCH_WEB: ("query",),
            ActionType.TYPE_TEXT: ("text",),
            ActionType.PRESS_KEY: ("key",),
            ActionType.SCROLL: ("direction",),
            ActionType.VOLUME: ("operation",),
            ActionType.MEDIA: ("operation",),
            ActionType.SYSTEM_SETTING: ("setting",),
            ActionType.ACCESSIBILITY_SETTING: ("setting",),
            ActionType.SWITCH_APP: ("target",),
            ActionType.WAIT: ("seconds",),
        }
        missing = [name for name in required.get(self.action, ()) if getattr(self, name) is None]
        if missing:
            raise ValueError(f"{self.action} requires: {', '.join(missing)}")
        if self.action == ActionType.SCROLL and self.direction not in {"UP", "DOWN", "TOP", "BOTTOM"}:
            raise ValueError("SCROLL direction must be UP, DOWN, TOP, or BOTTOM")
        return self


class DecisionContext(BaseModel):
    transcript: str
    frontmost_app: str | None = None
    installed_apps: list[str] = Field(default_factory=list)


def action_from_dict(value: dict[str, Any]) -> Action:
    """Validate an untrusted model response before it reaches an executor."""
    return Action.model_validate(value)
