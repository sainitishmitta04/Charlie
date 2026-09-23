from __future__ import annotations

import re

_COMMAND_START = r"(?:open|go\s+to|search|type|write|press|scroll|increase|decrease|mute|take|lock|turn|switch|wait)"
_COMPOUND = re.compile(rf"\s+and\s+(?={_COMMAND_START}\b)", re.IGNORECASE)


def split_compound(transcript: str) -> list[str]:
    """Split only between recognizable command starts, preserving text payloads."""
    parts = [part.strip() for part in _COMPOUND.split(transcript.strip()) if part.strip()]
    return parts or [transcript.strip()]