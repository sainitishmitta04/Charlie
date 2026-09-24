from types import SimpleNamespace

import numpy as np
import pytest
from app.audio.microphone import MicrophoneError, SoundDeviceMicrophone
from app.audio.timing import VoiceTiming
from app.audio.wake_word import WhisperWakeWordDetector
from app.main import run_wake_word
from app.voice_state import VoiceState, VoiceStateMachine


@pytest.mark.parametrize("text", ["Charlie", "charlie", "CHARLIE", "Charlie!", "Charlie.", "Hey Charlie"])
def test_wake_word_is_case_insensitive(text):
    assert WhisperWakeWordDetector().match(text).detected


def test_wake_word_extracts_command_and_does_not_include_it():
    match = WhisperWakeWordDetector().match("Charlie, open Chrome")
    assert match.detected
    assert match.command == "open Chrome"
    assert WhisperWakeWordDetector().match("Hey Charlie, open Chrome").command == "open Chrome"
    assert not WhisperWakeWordDetector().match("open Chrome").detected
    assert not WhisperWakeWordDetector().match("charming charliehorse").detected


class FakeInputStream:
    def __init__(self, chunks):
        self.chunks = iter(chunks)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, frames):
        return next(self.chunks), None


def test_microphone_stops_after_silence_and_keeps_preroll(monkeypatch, tmp_path):
    silence = np.zeros((1600, 1), dtype=np.int16)
    speech = np.full((1600, 1), 2000, dtype=np.int16)
    chunks = [silence, speech, silence, silence]
    written = {}
    fake_sounddevice = SimpleNamespace(
        default=SimpleNamespace(device=(0, 1)),
        InputStream=lambda **kwargs: FakeInputStream(chunks),
    )
    fake_soundfile = SimpleNamespace(write=lambda path, audio, rate, subtype: written.update(audio=audio, rate=rate))
    monkeypatch.setitem(__import__("sys").modules, "sounddevice", fake_sounddevice)
    monkeypatch.setitem(__import__("sys").modules, "soundfile", fake_soundfile)
    path = SoundDeviceMicrophone(
        max_record_seconds=5,
        min_record_seconds=0.1,
        silence_seconds=0.2,
        speech_threshold=0.01,
        preroll_seconds=0.1,
    ).record()
    assert written["rate"] == 16000
    assert len(written["audio"]) == 6400
    assert len(written["audio"]) == 4 * 1600
    path.unlink(missing_ok=True)


def test_microphone_raises_for_noise_free_timeout(monkeypatch):
    silence = np.zeros((1600, 1), dtype=np.int16)
    fake_sounddevice = SimpleNamespace(
        default=SimpleNamespace(device=(0, 1)),
        InputStream=lambda **kwargs: FakeInputStream([silence, silence]),
    )
    monkeypatch.setitem(__import__("sys").modules, "sounddevice", fake_sounddevice)
    monkeypatch.setitem(__import__("sys").modules, "soundfile", SimpleNamespace())
    with pytest.raises(MicrophoneError, match="No speech detected"):
        SoundDeviceMicrophone(max_record_seconds=0.2, min_record_seconds=0.1, silence_detection=True).record()


def test_microphone_rejects_calibrated_low_level_noise(monkeypatch):
    noise = np.full((1600, 1), 800, dtype=np.int16)
    fake_sounddevice = SimpleNamespace(
        default=SimpleNamespace(device=(0, 1)),
        InputStream=lambda **kwargs: FakeInputStream([noise, noise, noise, noise]),
    )
    monkeypatch.setitem(__import__("sys").modules, "sounddevice", fake_sounddevice)
    monkeypatch.setitem(__import__("sys").modules, "soundfile", SimpleNamespace())
    with pytest.raises(MicrophoneError, match="No speech detected"):
        SoundDeviceMicrophone(max_record_seconds=0.4, min_record_seconds=0.1).record()


def test_microphone_maximum_duration_is_a_hard_stop(monkeypatch):
    speech = np.full((1600, 1), 2000, dtype=np.int16)
    written = {}
    fake_sounddevice = SimpleNamespace(
        default=SimpleNamespace(device=(0, 1)),
        InputStream=lambda **kwargs: FakeInputStream([speech, speech, speech]),
    )
    monkeypatch.setitem(__import__("sys").modules, "sounddevice", fake_sounddevice)
    monkeypatch.setitem(
        __import__("sys").modules,
        "soundfile",
        SimpleNamespace(write=lambda path, audio, rate, subtype: written.update(audio=audio)),
    )
    microphone = SoundDeviceMicrophone(max_record_seconds=0.3, min_record_seconds=0.1, silence_seconds=0.2)
    path = microphone.record()
    assert microphone.last_stats.max_duration_reached
    assert not microphone.last_stats.speech_stopped
    assert len(written["audio"]) == 3 * 1600
    path.unlink(missing_ok=True)


def test_voice_timing_summary_is_readable():
    timing = VoiceTiming(
        recording_start=1,
        recording_end=2,
        whisper_start=2,
        whisper_end=2.5,
        decision_start=2.5,
        decision_end=3,
        executor_start=3,
        executor_end=3.1,
        total_start=1,
        total_end=3.1,
    )
    summary = timing.summary()
    assert "Recording:     1.00s" in summary
    assert "Total:         2.10s" in summary


def test_voice_state_machine_has_explicit_transitions():
    states = VoiceStateMachine()
    assert states.state == VoiceState.IDLE
    states.start_waiting()
    states.wake_detected()
    states.command_received()
    states.execution_started()
    states.reset()
    assert states.state == VoiceState.WAITING_FOR_WAKE_WORD
    with pytest.raises(RuntimeError):
        states.execution_started()


def test_wake_word_inline_command_uses_only_command_transcript(tmp_path):
    audio = tmp_path / "wake.wav"
    audio.write_bytes(b"audio")
    calls = []
    microphone = SimpleNamespace(record=lambda: audio)
    stt = SimpleNamespace(transcribe=lambda _: "Charlie, open Chrome")
    result = run_wake_word(
        dry_run=True,
        microphone=microphone,
        stt=stt,
        run_transcript=lambda transcript, dry: calls.append((transcript, dry)) or 0,
        max_cycles=1,
    )
    assert result == 0
    assert calls == [("open Chrome", True)]
    assert not audio.exists()


def test_non_wake_word_does_not_reach_command_pipeline(tmp_path):
    audio = tmp_path / "noise.wav"
    audio.write_bytes(b"audio")
    calls = []
    result = run_wake_word(
        dry_run=True,
        microphone=SimpleNamespace(record=lambda: audio),
        stt=SimpleNamespace(transcribe=lambda _: "Open Chrome"),
        run_transcript=lambda transcript, dry: calls.append((transcript, dry)) or 0,
        max_cycles=1,
    )
    assert result == 0
    assert calls == []
    assert not audio.exists()


def test_wake_word_alone_consumes_wake_audio_and_routes_next_utterance(tmp_path):
    wake_audio = tmp_path / "wake.wav"
    command_audio = tmp_path / "command.wav"
    wake_audio.write_bytes(b"wake")
    command_audio.write_bytes(b"command")
    wake_mic = SimpleNamespace(record=lambda: wake_audio)
    command_mic = SimpleNamespace(record=lambda: command_audio)
    transcripts = iter(["Charlie!", "Open Chrome"])
    calls = []
    result = run_wake_word(
        dry_run=True,
        microphone=wake_mic,
        command_microphone=command_mic,
        stt=SimpleNamespace(transcribe=lambda _: next(transcripts)),
        run_transcript=lambda transcript, dry: calls.append((transcript, dry)) or 0,
        max_cycles=1,
    )
    assert result == 0
    assert calls == [("Open Chrome", True)]
    assert not wake_audio.exists() and not command_audio.exists()


def test_empty_command_returns_to_waiting_without_reaching_pipeline(tmp_path):
    wake_audio = tmp_path / "wake.wav"
    command_audio = tmp_path / "command.wav"
    wake_audio.write_bytes(b"wake")
    command_audio.write_bytes(b"command")
    calls = []
    result = run_wake_word(
        dry_run=True,
        microphone=SimpleNamespace(record=lambda: wake_audio),
        command_microphone=SimpleNamespace(record=lambda: command_audio),
        stt=SimpleNamespace(transcribe=lambda _: "Charlie" if _.name == "wake.wav" else ""),
        run_transcript=lambda transcript, dry: calls.append((transcript, dry)) or 0,
        max_cycles=1,
    )
    assert result == 0
    assert calls == []


def test_repeated_wake_word_is_consumed_during_command_capture(tmp_path):
    wake_audio = tmp_path / "wake.wav"
    command_audio = tmp_path / "command.wav"
    wake_audio.write_bytes(b"wake")
    command_audio.write_bytes(b"command")
    calls = []
    result = run_wake_word(
        dry_run=True,
        microphone=SimpleNamespace(record=lambda: wake_audio),
        command_microphone=SimpleNamespace(record=lambda: command_audio),
        stt=SimpleNamespace(transcribe=lambda _: "Charlie"),
        run_transcript=lambda transcript, dry: calls.append((transcript, dry)) or 0,
        max_cycles=1,
    )
    assert result == 0
    assert calls == []
