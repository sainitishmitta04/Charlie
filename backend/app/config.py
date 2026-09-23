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
CHARLIE_SAMPLE_RATE = int(env("CHARLIE_SAMPLE_RATE", "16000"))
