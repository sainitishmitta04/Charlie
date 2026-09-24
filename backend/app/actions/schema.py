from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ActionType(StrEnum):
    OPEN_APP = "OPEN_APP"
    OPEN_URL = "OPEN_URL"
    SEARCH_WEB = "SEARCH_WEB"
    SEARCH_CURRENT_SITE = "SEARCH_CURRENT_SITE"
    TYPE_TEXT = "TYPE_TEXT"
    PRESS_KEY = "PRESS_KEY"
    SCROLL = "SCROLL"
    VOLUME_UP = "VOLUME_UP"
    VOLUME_DOWN = "VOLUME_DOWN"
    MUTE = "MUTE"
    UNMUTE = "UNMUTE"
    SCREENSHOT = "SCREENSHOT"
    LOCK_SCREEN = "LOCK_SCREEN"
    DARK_MODE_ON = "DARK_MODE_ON"
    DARK_MODE_OFF = "DARK_MODE_OFF"
    SYSTEM_SETTINGS = "SYSTEM_SETTINGS"
    OPEN_SYSTEM_SETTINGS = "OPEN_SYSTEM_SETTINGS"
    OPEN_ACCESSIBILITY_SETTINGS = "OPEN_ACCESSIBILITY_SETTINGS"
    OPEN_DISPLAY_SETTINGS = "OPEN_DISPLAY_SETTINGS"
    OPEN_SOUND_SETTINGS = "OPEN_SOUND_SETTINGS"
    OPEN_BLUETOOTH_SETTINGS = "OPEN_BLUETOOTH_SETTINGS"
    OPEN_WIFI_SETTINGS = "OPEN_WIFI_SETTINGS"
    OPEN_PRIVACY_SETTINGS = "OPEN_PRIVACY_SETTINGS"
    SWITCH_APP = "SWITCH_APP"
    CLOSE_APP = "CLOSE_APP"
    QUIT_APP = "QUIT_APP"
    ACCESSIBILITY_CLICK = "ACCESSIBILITY_CLICK"
    ACCESSIBILITY_SELECT = "ACCESSIBILITY_SELECT"
    ACCESSIBILITY_FOCUS = "ACCESSIBILITY_FOCUS"
    ACCESSIBILITY_READ_FOCUSED = "ACCESSIBILITY_READ_FOCUSED"
    ACCESSIBILITY_INSPECT = "ACCESSIBILITY_INSPECT"
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
    modifiers: list[str] = Field(default_factory=list)
    role: str | None = None
    seconds: float | None = Field(default=None, ge=0, le=60)

    @model_validator(mode="after")
    def validate_arguments(self) -> Action:
        required: dict[ActionType, tuple[str, ...]] = {
            ActionType.OPEN_APP: ("target",),
            ActionType.CLOSE_APP: ("target",),
            ActionType.QUIT_APP: ("target",),
            ActionType.OPEN_URL: ("url",),
            ActionType.SEARCH_WEB: ("query",),
            ActionType.SEARCH_CURRENT_SITE: ("query", "url"),
            ActionType.TYPE_TEXT: ("text",),
            ActionType.PRESS_KEY: ("key",),
            ActionType.SCROLL: ("direction",),
            ActionType.SWITCH_APP: ("target",),
            ActionType.SYSTEM_SETTINGS: ("setting",),
            ActionType.OPEN_SYSTEM_SETTINGS: (),
            ActionType.OPEN_ACCESSIBILITY_SETTINGS: (),
            ActionType.OPEN_DISPLAY_SETTINGS: (),
            ActionType.OPEN_SOUND_SETTINGS: (),
            ActionType.OPEN_BLUETOOTH_SETTINGS: (),
            ActionType.OPEN_WIFI_SETTINGS: (),
            ActionType.OPEN_PRIVACY_SETTINGS: (),
            ActionType.ACCESSIBILITY_CLICK: ("target",),
            ActionType.ACCESSIBILITY_SELECT: ("target",),
            ActionType.ACCESSIBILITY_FOCUS: ("target",),
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
        allowed_keys = {
            "ENTER", "RETURN", "ESCAPE", "TAB", "SPACE", "BACKSPACE", "DELETE", "UP", "DOWN", "LEFT", "RIGHT",
        }
        if self.action == ActionType.PRESS_KEY and self.key not in allowed_keys and not re.fullmatch(r"[A-Za-z0-9]", self.key or ""):
            raise ValueError("PRESS_KEY key is not supported")
        if any(modifier not in {"COMMAND", "CONTROL", "OPTION", "SHIFT"} for modifier in self.modifiers):
            raise ValueError("PRESS_KEY modifiers are not supported")
        if self.action == ActionType.TYPE_TEXT and not self.text:
            raise ValueError("TYPE_TEXT requires non-empty text")
        if self.action == ActionType.WAIT and not 0.1 <= self.seconds <= 10:
            raise ValueError("WAIT seconds must be between 0.1 and 10")
        return self


class DecisionContext(BaseModel):
    transcript: str
    frontmost_app: str | None = None
    installed_apps: list[str] = Field(default_factory=list)
    accessible_targets: list[str] = Field(default_factory=list)
    session_context: dict[str, Any] = Field(default_factory=dict)


def action_from_dict(value: dict[str, Any]) -> Action:
    """Validate an untrusted model response before it reaches an executor."""
    return Action.model_validate(value)
