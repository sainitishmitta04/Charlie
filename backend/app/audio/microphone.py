from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app import config


class MicrophoneError(RuntimeError):
    """A local microphone could not record audio."""


@dataclass(frozen=True)
class RecordingStats:
    speech_started: bool
    speech_stopped: bool
    silence_duration: float
    recording_duration: float
    max_duration_reached: bool


class Microphone(Protocol):
    def record(self) -> Path:
        """Record one command and return a local WAV file."""


class SoundDeviceMicrophone:
    """Record one fixed-length mono PCM clip through the default input device."""

    def __init__(
        self,
        max_record_seconds: float = config.CHARLIE_MAX_RECORD_SECONDS,
        sample_rate: int = config.CHARLIE_SAMPLE_RATE,
        min_record_seconds: float = config.CHARLIE_MIN_RECORD_SECONDS,
        silence_seconds: float = config.CHARLIE_SILENCE_SECONDS,
        speech_threshold: float = config.CHARLIE_SPEECH_THRESHOLD,
        preroll_seconds: float = config.CHARLIE_PREROLL_SECONDS,
        silence_detection: bool = config.CHARLIE_SILENCE_DETECTION,
    ) -> None:
        if max_record_seconds <= 0:
            raise ValueError("Microphone maximum duration must be greater than zero")
        if min_record_seconds < 0 or min_record_seconds > max_record_seconds:
            raise ValueError("Microphone minimum duration must be between zero and the maximum")
        if silence_seconds <= 0 or speech_threshold < 0 or preroll_seconds < 0:
            raise ValueError("Microphone silence settings must be non-negative and usable")
        if sample_rate <= 0:
            raise ValueError("Microphone sample rate must be greater than zero")
        self.max_record_seconds = max_record_seconds
        self.sample_rate = sample_rate
        self.min_record_seconds = min_record_seconds
        self.silence_seconds = silence_seconds
        self.speech_threshold = speech_threshold
        self.preroll_seconds = preroll_seconds
        self.silence_detection = silence_detection
        self.last_stats = RecordingStats(False, False, 0.0, 0.0, False)

    def record(self) -> Path:
        try:
            import sounddevice as sd  # type: ignore
            import soundfile as sf  # type: ignore
        except ImportError as error:
            raise MicrophoneError("Microphone support requires sounddevice and soundfile") from error

        try:
            device = sd.default.device
            if device is None or device[0] is None or device[0] < 0:
                raise MicrophoneError("No default microphone was found")
            if not self.silence_detection or not hasattr(sd, "InputStream"):
                frames = round(self.max_record_seconds * self.sample_rate)
                audio = sd.rec(frames, samplerate=self.sample_rate, channels=1, dtype="int16")
                sd.wait()
                self.last_stats = RecordingStats(True, False, 0.0, self.max_record_seconds, True)
            else:
                audio = self._record_until_silence(sd)
        except PermissionError as error:
            raise MicrophoneError(
                "Microphone permission denied. Grant Terminal or Charlie access in "
                "System Settings -> Privacy & Security -> Microphone."
            ) from error
        except MicrophoneError:
            raise
        except Exception as error:
            raise MicrophoneError(f"Microphone recording failed: {error}") from error

        with tempfile.NamedTemporaryFile(prefix="charlie-", suffix=".wav", delete=False) as handle:
            path = Path(handle.name)
        try:
            sf.write(path, audio, self.sample_rate, subtype="PCM_16")
        except Exception as error:
            path.unlink(missing_ok=True)
            raise MicrophoneError(f"Could not save microphone recording: {error}") from error
        if config.CHARLIE_AUDIO_DEBUG:
            stats = self.last_stats
            print(
                "Audio: "
                f"speech_started={stats.speech_started} "
                f"speech_stopped={stats.speech_stopped} "
                f"silence_duration={stats.silence_duration:.2f}s "
                f"recording_duration={stats.recording_duration:.2f}s "
                f"max_duration_reached={stats.max_duration_reached}"
            )
        return path

    def _record_until_silence(self, sounddevice: object):
        try:
            import numpy as np
        except ImportError as error:
            raise MicrophoneError("Silence detection requires numpy") from error

        chunk_frames = max(1, round(self.sample_rate * 0.1))
        max_chunks = max(1, round(self.max_record_seconds / 0.1))
        min_chunks = round(self.min_record_seconds / 0.1)
        silence_chunks = max(1, round(self.silence_seconds / 0.1))
        preroll_chunks = max(0, round(self.preroll_seconds / 0.1))
        chunks: list[object] = []
        speech_started = False
        speech_start_index = 0
        quiet_count = 0
        stopped_on_silence = False
        baseline_rms: list[float] = []
        calibration_chunks = max(1, round(0.3 / 0.1))
        effective_threshold = self.speech_threshold

        with sounddevice.InputStream(samplerate=self.sample_rate, channels=1, dtype="int16") as stream:
            for index in range(max_chunks):
                chunk, _ = stream.read(chunk_frames)
                chunk = np.asarray(chunk)
                chunks.append(chunk.copy())
                rms = float(np.sqrt(np.mean(np.square(chunk.astype(np.float32) / 32768.0))))
                if not speech_started and len(baseline_rms) < calibration_chunks:
                    baseline_rms.append(rms)
                    # A loud first chunk is likely the start of speech; retain it
                    # while still allowing ordinary room noise to calibrate.
                    if rms >= self.speech_threshold * 4:
                        speech_started = True
                        speech_start_index = max(0, index - preroll_chunks)
                        quiet_count = 0
                    continue
                if not speech_started:
                    noise_floor = float(np.median(baseline_rms))
                    effective_threshold = max(self.speech_threshold, noise_floor * 2.0)
                if rms >= effective_threshold:
                    if not speech_started:
                        speech_start_index = max(0, index - preroll_chunks)
                    speech_started = True
                    quiet_count = 0
                elif speech_started and index - speech_start_index + 1 >= min_chunks:
                    quiet_count += 1
                if speech_started and quiet_count >= silence_chunks:
                    stopped_on_silence = True
                    break

        recording_duration = min((index + 1) * 0.1, self.max_record_seconds)
        silence_duration = quiet_count * 0.1
        self.last_stats = RecordingStats(
            speech_started=speech_started,
            speech_stopped=stopped_on_silence,
            silence_duration=silence_duration,
            recording_duration=recording_duration,
            max_duration_reached=not stopped_on_silence and index + 1 >= max_chunks,
        )
        if not speech_started:
            raise MicrophoneError("No speech detected.")
        selected = chunks[speech_start_index:]
        return np.concatenate(selected, axis=0)

    @staticmethod
    def available_devices() -> list[str]:
        try:
            import sounddevice as sd  # type: ignore

            return [str(device["name"]) for device in sd.query_devices() if int(device["max_input_channels"]) > 0]
        except ImportError as error:
            raise MicrophoneError("Microphone support requires sounddevice") from error
        except Exception as error:
            raise MicrophoneError(f"Could not inspect microphones: {error}") from error
