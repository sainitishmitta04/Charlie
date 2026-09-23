from __future__ import annotations

import subprocess
import time
from typing import ClassVar, Protocol
from urllib.parse import quote_plus


class MacOSExecutor(Protocol):
    def execute(self, action_name: str, action: object) -> str:
        """Execute a validated action without accepting model-generated commands."""


class NativeMacOSExecutor:
    _KEY_CODES: ClassVar[dict[str, int]] = {
        "ENTER": 36, "ESCAPE": 53, "TAB": 48, "SPACE": 49, "BACKSPACE": 51,
        "DELETE": 117, "UP": 126, "DOWN": 125, "LEFT": 123, "RIGHT": 124,
    }

    def execute(self, action_name: str, action: object) -> str:
        method = getattr(self, f"_{action_name.lower()}", None)
        if method is None:
            raise ValueError(f"Unsupported macOS action: {action_name}")
        return method(action)

    @staticmethod
    def _run(command: list[str]) -> None:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @staticmethod
    def _osascript(script: str) -> None:
        NativeMacOSExecutor._run(["osascript", "-e", script])

    def _open_app(self, action: object) -> str:
        self._run(["open", "-a", action.target])
        return f"Opening {action.target}."

    def _switch_app(self, action: object) -> str:
        return self._open_app(action)

    def _open_url(self, action: object) -> str:
        url = action.url if action.url.startswith(("http://", "https://")) else f"https://{action.url}"
        self._run(["open", url])
        return f"Opening {url}."

    def _search_web(self, action: object) -> str:
        engine = action.engine or "google"
        base = "https://www.youtube.com/results?search_query=" if engine == "youtube" else "https://www.google.com/search?q="
        self._run(["open", f"{base}{quote_plus(action.query)}"])
        return f"Searching {engine} for {action.query}."

    def _type_text(self, action: object) -> str:
        text = action.text.replace("\\", "\\\\").replace('"', '\\"')
        self._osascript(f'tell application "System Events" to keystroke "{text}"')
        return "Done."

    def _press_key(self, action: object) -> str:
        self._osascript(f'tell application "System Events" to key code {self._KEY_CODES[action.key]}')
        return f"Pressed {action.key.lower()}."

    def _scroll(self, action: object) -> str:
        key = {"UP": 126, "DOWN": 125, "TOP": 126, "BOTTOM": 125}[action.direction]
        modifier = " using {command down}" if action.direction in {"TOP", "BOTTOM"} else ""
        for _ in range(action.amount or 5):
            self._osascript(f'tell application "System Events" to key code {key}{modifier}')
        return "Done."

    def _volume_up(self, action: object) -> str:
        self._osascript("set volume output volume ((output volume of (get volume settings)) + 10)")
        return "Volume increased."

    def _volume_down(self, action: object) -> str:
        self._osascript("set volume output volume ((output volume of (get volume settings)) - 10)")
        return "Volume decreased."

    def _mute(self, action: object) -> str:
        self._osascript("set volume output muted not (output muted of (get volume settings))")
        return "Mute toggled."

    def _screenshot(self, action: object) -> str:
        path = f"{__import__('pathlib').Path.home()}/Desktop/Charlie-{int(time.time())}.png"
        self._run(["screencapture", path])
        return f"Screenshot saved to {path}."

    def _lock_screen(self, action: object) -> str:
        self._osascript('tell application "System Events" to keystroke "q" using {control down, command down}')
        return "Mac locked."

    def _dark_mode_on(self, action: object) -> str:
        self._osascript("tell application \"System Events\" to tell appearance preferences to set dark mode to true")
        return "Dark mode enabled."

    def _dark_mode_off(self, action: object) -> str:
        self._osascript("tell application \"System Events\" to tell appearance preferences to set dark mode to false")
        return "Dark mode disabled."

    def _wait(self, action: object) -> str:
        time.sleep(action.seconds)
        return "Done waiting."
