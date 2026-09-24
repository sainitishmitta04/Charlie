from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class WakeMatch:
    detected: bool
    command: str = ""


class WakeWordDetector(Protocol):
    def match(self, transcript: str) -> WakeMatch:
        ...


class WhisperWakeWordDetector:
    def __init__(self, wake_word: str = "Charlie") -> None:
        normalized = self._normalize(wake_word)
        if not normalized:
            raise ValueError("Wake word must not be empty")
        self.wake_word = normalized

    def match(self, transcript: str) -> WakeMatch:
        original = " ".join(transcript.strip().split())
        normalized = self._normalize(transcript)
        wake_forms = (self.wake_word, f"hey {self.wake_word}")
        if normalized in wake_forms:
            return WakeMatch(True)
        for wake_form in wake_forms:
            if normalized.startswith(wake_form + " "):
                original_prefix = original[: len(wake_form)]
                if self._normalize(original_prefix) == wake_form:
                    return WakeMatch(True, original[len(original_prefix):].strip(" ,.!?"))
        return WakeMatch(False)

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(re.sub(r"[^\w\s]", " ", value.casefold()).split())
