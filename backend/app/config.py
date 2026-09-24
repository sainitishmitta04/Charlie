from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


TYPESAFE_API_KEY = env("TYPESAFE_API_KEY")
TYPESAFE_URL = env("TYPESAFE_URL", "https://api.typesafe.ai/v1/systemone")
JEV_MODEL = env("TYPESAFE_MODEL", "jev-latest")
WAKE_WORD = env("CHARLIE_WAKE_WORD", "Charlie")
CHARLIE_WHISPER_BIN = env("CHARLIE_WHISPER_BIN", "whisper-cli")
CHARLIE_WHISPER_MODEL = env("CHARLIE_WHISPER_MODEL", "models/ggml-base.en.bin")
CHARLIE_RECORD_SECONDS = float(env("CHARLIE_RECORD_SECONDS", "5"))
CHARLIE_MAX_RECORD_SECONDS = float(env("CHARLIE_MAX_RECORD_SECONDS", str(CHARLIE_RECORD_SECONDS)))
CHARLIE_MIN_RECORD_SECONDS = float(env("CHARLIE_MIN_RECORD_SECONDS", "0.5"))
CHARLIE_SILENCE_SECONDS = float(env("CHARLIE_SILENCE_SECONDS", "0.7"))
CHARLIE_SPEECH_THRESHOLD = float(env("CHARLIE_SPEECH_THRESHOLD", "0.015"))
CHARLIE_PREROLL_SECONDS = float(env("CHARLIE_PREROLL_SECONDS", "0.2"))
CHARLIE_WAKE_CHUNK_SECONDS = float(env("CHARLIE_WAKE_CHUNK_SECONDS", "2"))
CHARLIE_SILENCE_DETECTION = env("CHARLIE_SILENCE_DETECTION", "1").lower() not in {"0", "false", "no"}
CHARLIE_AUDIO_DEBUG = env("CHARLIE_AUDIO_DEBUG", "0").lower() not in {"0", "false", "no"}
CHARLIE_CONTEXT_TIMEOUT_SECONDS = float(env("CHARLIE_CONTEXT_TIMEOUT_SECONDS", "300"))
CHARLIE_CONVERSATION_TIMEOUT_SECONDS = float(env("CHARLIE_CONVERSATION_TIMEOUT_SECONDS", "8"))
CHARLIE_SAMPLE_RATE = int(env("CHARLIE_SAMPLE_RATE", "16000"))
