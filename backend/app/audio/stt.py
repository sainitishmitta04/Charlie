from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

from app import config


class SpeechToTextError(RuntimeError):
    """A local whisper.cpp transcription could not be completed."""


class SpeechToText(Protocol):
    def transcribe(self, audio_path: str | Path) -> str:
        """Convert a local audio file into a clean transcript."""


class WhisperSTT:
    def __init__(self, executable: str | Path | None = None, model: str | Path | None = None) -> None:
        self.executable = self._resolve_executable(executable or config.CHARLIE_WHISPER_BIN)
        self.model = self._resolve_model(model or config.CHARLIE_WHISPER_MODEL)

    @staticmethod
    def _resolve_executable(value: str | Path) -> Path:
        configured = str(value).strip()
        if not configured:
            raise SpeechToTextError(
                "Whisper executable not found. Configure CHARLIE_WHISPER_BIN=/path/to/whisper-cli."
            )
        path = Path(configured).expanduser()
        resolved = path if path.parent != Path(".") else Path(shutil.which(configured) or "")
        if not resolved.is_file() or not resolved.stat().st_mode & 0o111:
            raise SpeechToTextError(
                f"Whisper executable not found: {configured}. "
                "Configure CHARLIE_WHISPER_BIN=/path/to/whisper-cli."
            )
        return resolved

    @staticmethod
    def _resolve_model(value: str | Path) -> Path:
        configured = str(value).strip()
        if not configured:
            raise SpeechToTextError(
                "Whisper model not found. Configure CHARLIE_WHISPER_MODEL=models/ggml-base.en.bin."
            )
        path = Path(configured).expanduser()
        resolved = path if path.is_absolute() else config.PROJECT_ROOT / path
        if not resolved.is_file():
            raise SpeechToTextError(
                f"Whisper model not found: {resolved}. "
                "Please download the base.en model before using voice mode."
            )
        return resolved

    def transcribe(self, audio_path: str | Path) -> str:
        audio = Path(audio_path).expanduser()
        if not audio.is_file():
            raise SpeechToTextError(f"Recorded audio file not found: {audio}")

        with tempfile.TemporaryDirectory(prefix="charlie-whisper-") as directory:
            output_base = Path(directory) / "transcript"
            command = [
                str(self.executable),
                "-m", str(self.model),
                "-f", str(audio),
                "-otxt",
                "-of", str(output_base),
                "-nt",
            ]
            try:
                result = subprocess.run(command, capture_output=True, text=True, check=False)
            except OSError as error:
                raise SpeechToTextError(f"Could not start whisper.cpp: {error}") from error
            if result.returncode != 0:
                detail = (result.stderr or result.stdout).strip()
                raise SpeechToTextError(f"whisper.cpp failed: {detail or 'unknown error'}")

            output_file = output_base.with_suffix(".txt")
            raw = output_file.read_text(encoding="utf-8") if output_file.exists() else result.stdout
            transcript = " ".join(raw.split())
            if not transcript:
                raise SpeechToTextError("No speech detected.")
            return transcript
