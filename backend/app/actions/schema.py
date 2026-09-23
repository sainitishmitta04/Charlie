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
    VOLUME_UP = "VOLUME_UP"
    VOLUME_DOWN = "VOLUME_DOWN"
    MUTE = "MUTE"
    SCREENSHOT = "SCREENSHOT"
    LOCK_SCREEN = "LOCK_SCREEN"
    DARK_MODE_ON = "DARK_MODE_ON"
    DARK_MODE_OFF = "DARK_MODE_OFF"
    SYSTEM_SETTINGS = "SYSTEM_SETTINGS"
    SWITCH_APP = "SWITCH_APP"
    WAIT = "WAIT"


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ActionType
    target: str | None = Field(default=None, min_length=1)
    url: str | None = Field(default=None, min_length=1)
    query: str | None = None
    text: str | None = None
    key: str | None = None
    direction: str | None = None
    amount: int | None = Field(default=None, ge=1, le=20)
    engine: str | None = None
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
            ActionType.SWITCH_APP: ("target",),
            ActionType.SYSTEM_SETTINGS: ("setting",),
            ActionType.WAIT: ("seconds",),
        }
        missing = [name for name in required.get(self.action, ()) if getattr(self, name) is None]
        if missing:
            raise ValueError(f"{self.action} requires: {', '.join(missing)}")
        if self.action == ActionType.SCROLL and self.direction not in {"UP", "DOWN", "TOP", "BOTTOM"}:
            raise ValueError("SCROLL direction must be UP, DOWN, TOP, or BOTTOM")
        if self.action == ActionType.OPEN_URL and not self.url.startswith(("http://", "https://")):
            raise ValueError("OPEN_URL url must start with http:// or https://")
        if self.action == ActionType.SYSTEM_SETTINGS and self.setting not in {
            "ACCESSIBILITY", "DISPLAY", "SOUND", "BLUETOOTH", "WI_FI", "PRIVACY_SECURITY",
        }:
            raise ValueError("SYSTEM_SETTINGS setting is not supported")
        if self.action == ActionType.PRESS_KEY and self.key not in {
            "ENTER", "ESCAPE", "TAB", "SPACE", "BACKSPACE", "DELETE", "UP", "DOWN", "LEFT", "RIGHT",
        }:
            raise ValueError("PRESS_KEY key is not supported")
        return self


class DecisionContext(BaseModel):
    transcript: str
    frontmost_app: str | None = None
    installed_apps: list[str] = Field(default_factory=list)


def action_from_dict(value: dict[str, Any]) -> Action:
    """Validate an untrusted model response before it reaches an executor."""
    return Action.model_validate(value)
