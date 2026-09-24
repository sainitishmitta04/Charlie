from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter


@dataclass
class VoiceTiming:
    recording_start: float | None = None
    recording_end: float | None = None
    audio_file_created: float | None = None
    whisper_start: float | None = None
    whisper_end: float | None = None
    transcript_available: float | None = None
    decision_start: float | None = None
    decision_end: float | None = None
    executor_start: float | None = None
    executor_end: float | None = None
    total_start: float | None = None
    total_end: float | None = None

    def mark(self, name: str) -> None:
        setattr(self, name, perf_counter())

    @staticmethod
    def _duration(start: float | None, end: float | None) -> float | None:
        return end - start if start is not None and end is not None else None

    def summary(self) -> str:
        recording = self._duration(self.recording_start, self.recording_end)
        whisper = self._duration(self.whisper_start, self.whisper_end)
        decision = self._duration(self.decision_start, self.decision_end)
        execution = self._duration(self.executor_start, self.executor_end)
        total = self._duration(self.total_start, self.total_end)
        return (
            "Voice timing:\n"
            f"  Recording:     {recording or 0:.2f}s\n"
            f"  Whisper:       {whisper or 0:.2f}s\n"
            f"  Decision:      {decision or 0:.2f}s\n"
            f"  Execution:     {execution or 0:.2f}s\n"
            f"  Total:         {total or 0:.2f}s"
        )


class TimingContext:
    def __init__(self) -> None:
        self.timing = VoiceTiming()

    def __enter__(self) -> VoiceTiming:
        self.timing.mark("total_start")
        return self.timing

    def __exit__(self, *_: object) -> None:
        self.timing.mark("total_end")
