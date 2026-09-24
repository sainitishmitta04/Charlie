from __future__ import annotations

from enum import StrEnum


class VoiceState(StrEnum):
    IDLE = "IDLE"
    WAITING_FOR_WAKE_WORD = "WAITING_FOR_WAKE_WORD"
    LISTENING_FOR_COMMAND = "LISTENING_FOR_COMMAND"
    PROCESSING = "PROCESSING"
    EXECUTING = "EXECUTING"
    CONVERSATION_ACTIVE = "CONVERSATION_ACTIVE"


class VoiceStateMachine:
    def __init__(self) -> None:
        self.state = VoiceState.IDLE

    def start_waiting(self) -> None:
        self._transition(VoiceState.WAITING_FOR_WAKE_WORD)

    def wake_detected(self) -> None:
        self._transition(VoiceState.LISTENING_FOR_COMMAND)

    def command_received(self) -> None:
        self._transition(VoiceState.PROCESSING)

    def execution_started(self) -> None:
        self._transition(VoiceState.EXECUTING)

    def conversation_started(self) -> None:
        self._transition(VoiceState.CONVERSATION_ACTIVE)

    def follow_up_started(self) -> None:
        self._transition(VoiceState.LISTENING_FOR_COMMAND)

    def follow_up_failed(self) -> None:
        self._transition(VoiceState.CONVERSATION_ACTIVE)

    def conversation_ended(self) -> None:
        self._transition(VoiceState.WAITING_FOR_WAKE_WORD)

    def reset(self) -> None:
        self._transition(VoiceState.WAITING_FOR_WAKE_WORD)

    def _transition(self, next_state: VoiceState) -> None:
        allowed = {
            VoiceState.IDLE: {VoiceState.WAITING_FOR_WAKE_WORD},
            VoiceState.WAITING_FOR_WAKE_WORD: {VoiceState.LISTENING_FOR_COMMAND},
            VoiceState.LISTENING_FOR_COMMAND: {VoiceState.PROCESSING, VoiceState.WAITING_FOR_WAKE_WORD, VoiceState.CONVERSATION_ACTIVE},
            VoiceState.PROCESSING: {VoiceState.EXECUTING, VoiceState.WAITING_FOR_WAKE_WORD},
            VoiceState.EXECUTING: {VoiceState.WAITING_FOR_WAKE_WORD, VoiceState.CONVERSATION_ACTIVE},
            VoiceState.CONVERSATION_ACTIVE: {VoiceState.LISTENING_FOR_COMMAND, VoiceState.WAITING_FOR_WAKE_WORD},
        }
        if next_state not in allowed[self.state]:
            raise RuntimeError(f"Invalid voice state transition: {self.state} -> {next_state}")
        self.state = next_state
