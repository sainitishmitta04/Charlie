from __future__ import annotations

import re

_TERMINAL_PUNCTUATION = ".,!?;:…"


def normalize_voice_command(transcript: str) -> str:
    """Normalize a transcript for exact command matching, never for text entry."""
    normalized = " ".join(transcript.strip().split()).casefold()
    return normalized.rstrip(_TERMINAL_PUNCTUATION).rstrip()


def normalize_stop_command(transcript: str) -> str:
    """Normalize punctuation and whitespace for exact conversation stop matching."""
    normalized = normalize_voice_command(transcript)
    return " ".join(re.sub(r"[^\w\s]", "", normalized).split())


_KEY_COMMANDS = {
    "enter": "ENTER",
    "press enter": "ENTER",
    "hit enter": "ENTER",
    "return": "RETURN",
    "press return": "RETURN",
    "hit return": "RETURN",
    "next line": "ENTER",
    "new line": "ENTER",
    "tab": "TAB",
    "press tab": "TAB",
    "hit tab": "TAB",
    "backspace": "BACKSPACE",
    "press backspace": "BACKSPACE",
    "hit backspace": "BACKSPACE",
    "delete": "DELETE",
    "press delete": "DELETE",
    "hit delete": "DELETE",
    "escape": "ESCAPE",
    "esc": "ESCAPE",
    "press escape": "ESCAPE",
    "hit escape": "ESCAPE",
    "space": "SPACE",
    "press space": "SPACE",
    "hit space": "SPACE",
    "up": "UP",
    "arrow up": "UP",
    "press arrow up": "UP",
    "press up arrow": "UP",
    "down": "DOWN",
    "arrow down": "DOWN",
    "press arrow down": "DOWN",
    "press down arrow": "DOWN",
    "left": "LEFT",
    "arrow left": "LEFT",
    "press arrow left": "LEFT",
    "press left arrow": "LEFT",
    "right": "RIGHT",
    "arrow right": "RIGHT",
    "press arrow right": "RIGHT",
    "press right arrow": "RIGHT",
}


def deterministic_key_command(transcript: str) -> str | None:
    """Return an allowlisted key for an exact phrase, or None for Jev/text handling."""
    return _KEY_COMMANDS.get(normalize_voice_command(transcript))