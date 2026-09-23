from pathlib import Path
from types import SimpleNamespace

import pytest
from app.audio.microphone import MicrophoneError, SoundDeviceMicrophone
from app.audio.stt import SpeechToTextError, WhisperSTT
from app.main import run_voice


class FakeMicrophone:
    def __init__(self, path: Path):
        self.path = path
        self.called = False

    def record(self) -> Path:
        self.called = True
        return self.path


class FakeSTT:
    def __init__(self, transcript: str):
        self.transcript = transcript
        self.audio_path = None

    def transcribe(self, audio_path: Path) -> str:
        self.audio_path = audio_path
        return self.transcript


def make_whisper_files(tmp_path: Path) -> tuple[Path, Path]:
    executable = tmp_path / "whisper-cli"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o755)
    model = tmp_path / "ggml-base.en.bin"
    model.write_bytes(b"model")
    return executable, model


def test_whisper_validates_executable_and_model(tmp_path):
    executable, model = make_whisper_files(tmp_path)
    whisper = WhisperSTT(executable, model)
    assert whisper.executable == executable
    assert whisper.model == model

    with pytest.raises(SpeechToTextError, match="executable not found"):
        WhisperSTT(tmp_path / "missing-cli", model)
    with pytest.raises(SpeechToTextError, match="model not found"):
        WhisperSTT(executable, tmp_path / "missing-model.bin")


def test_whisper_successfully_reads_local_output(monkeypatch, tmp_path):
    executable, model = make_whisper_files(tmp_path)
    audio = tmp_path / "recording.wav"
    audio.write_bytes(b"wav")

    def fake_run(command, **kwargs):
        output_base = Path(command[command.index("-of") + 1])
        output_base.with_suffix(".txt").write_text("  open Chrome\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.audio.stt.subprocess.run", fake_run)
    assert WhisperSTT(executable, model).transcribe(audio) == "open Chrome"


def test_whisper_rejects_empty_and_failed_transcription(monkeypatch, tmp_path):
    executable, model = make_whisper_files(tmp_path)
    audio = tmp_path / "recording.wav"
    audio.write_bytes(b"wav")

    def empty_run(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout="  ", stderr="")

    monkeypatch.setattr("app.audio.stt.subprocess.run", empty_run)
    with pytest.raises(SpeechToTextError, match="No speech detected"):
        WhisperSTT(executable, model).transcribe(audio)

    def failed_run(command, **kwargs):
        return SimpleNamespace(returncode=2, stdout="", stderr="bad audio")

    monkeypatch.setattr("app.audio.stt.subprocess.run", failed_run)
    with pytest.raises(SpeechToTextError, match="bad audio"):
        WhisperSTT(executable, model).transcribe(audio)


def test_microphone_records_a_local_wav(monkeypatch):
    recorded = object()
    written = {}
    fake_sounddevice = SimpleNamespace(
        default=SimpleNamespace(device=(0, 1)),
        rec=lambda *args, **kwargs: recorded,
        wait=lambda: None,
    )
    fake_soundfile = SimpleNamespace(write=lambda path, audio, rate, subtype: written.update(
        path=path, audio=audio, rate=rate, subtype=subtype
    ))
    monkeypatch.setitem(__import__("sys").modules, "sounddevice", fake_sounddevice)
    monkeypatch.setitem(__import__("sys").modules, "soundfile", fake_soundfile)
    path = SoundDeviceMicrophone(1, 16000).record()
    assert path.suffix == ".wav"
    assert written["audio"] is recorded
    path.unlink(missing_ok=True)


def test_microphone_reports_missing_default_device(monkeypatch):
    fake_sounddevice = SimpleNamespace(default=SimpleNamespace(device=(-1, -1)))
    fake_soundfile = SimpleNamespace()
    monkeypatch.setitem(__import__("sys").modules, "sounddevice", fake_sounddevice)
    monkeypatch.setitem(__import__("sys").modules, "soundfile", fake_soundfile)
    with pytest.raises(MicrophoneError, match="No default microphone"):
        SoundDeviceMicrophone().record()


def test_voice_uses_transcript_pipeline_and_cleans_audio(tmp_path):
    audio = tmp_path / "recording.wav"
    audio.write_bytes(b"wav")
    microphone = FakeMicrophone(audio)
    stt = FakeSTT("open Chrome")
    calls = []

    def fake_pipeline(transcript: str, dry_run: bool) -> int:
        calls.append((transcript, dry_run))
        return 0

    assert run_voice(True, microphone, stt, fake_pipeline) == 0
    assert calls == [("open Chrome", True)]
    assert stt.audio_path == audio
    assert not audio.exists()


def test_voice_does_not_route_empty_transcript(tmp_path):
    audio = tmp_path / "recording.wav"
    audio.write_bytes(b"wav")
    calls = []
    assert run_voice(False, FakeMicrophone(audio), FakeSTT("   "), lambda *_: calls.append(1) or 0) == 1
    assert calls == []
    assert not audio.exists()
