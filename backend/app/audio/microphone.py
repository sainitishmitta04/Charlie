from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Protocol


class MicrophoneError(RuntimeError):
    """A local microphone could not record audio."""


class Microphone(Protocol):
    def record(self) -> Path:
        """Record one command and return a local WAV file."""


class SoundDeviceMicrophone:
    """Record one fixed-length mono PCM clip through the default input device."""

    def __init__(self, duration_seconds: float = 5.0, sample_rate: int = 16_000) -> None:
        if duration_seconds <= 0:
            raise ValueError("Microphone duration must be greater than zero")
        if sample_rate <= 0:
            raise ValueError("Microphone sample rate must be greater than zero")
        self.duration_seconds = duration_seconds
        self.sample_rate = sample_rate

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
            frames = round(self.duration_seconds * self.sample_rate)
            audio = sd.rec(frames, samplerate=self.sample_rate, channels=1, dtype="int16")
            sd.wait()
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
        return path

    @staticmethod
    def available_devices() -> list[str]:
        try:
            import sounddevice as sd  # type: ignore

            return [str(device["name"]) for device in sd.query_devices() if int(device["max_input_channels"]) > 0]
        except ImportError as error:
            raise MicrophoneError("Microphone support requires sounddevice") from error
        except Exception as error:
            raise MicrophoneError(f"Could not inspect microphones: {error}") from error
