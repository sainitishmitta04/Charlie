# Charlie backend

Phase 6 keeps text input as the source of truth and adds responsive local voice interaction:

- `brain/`: decision engines. Jev is active; Laya has a reserved adapter.
- `actions/schema.py`: validated actions from an untrusted model response.
- `actions/registry.py` and `actions/macos.py`: the only macOS execution path.
- `actions/accessibility.py`: native AX-tree inspection and safe element actions.
- `audio/microphone.py`: one fixed-length local WAV recording.
- `audio/stt.py`: local whisper.cpp execution and transcript parsing.
- `audio/timing.py`: reusable voice pipeline timing measurements.
- `audio/wake_word.py`: local Whisper transcript wake-word matching.
- `voice_state.py`: explicit wake-word interaction states.

Installed applications are discovered from `/Applications`, `/System/Applications`,
and `~/Applications`. Switching uses the same validated app target as opening an app.
System Settings navigation uses fixed Apple preference URLs for Accessibility, Display,
Sound, Bluetooth, Wi-Fi, and Privacy & Security.

Run from the repository root:

```bash
source .venv/bin/activate
PYTHONPATH=backend python -m app.main --text "open Chrome" --dry-run
PYTHONPATH=backend python -m app.main --text "increase volume" --dry-run
PYTHONPATH=backend python -m app.main --text "open Chrome and go to YouTube" --dry-run
PYTHONPATH=backend python -m app.main --text "open Notes and type buy milk" --dry-run
PYTHONPATH=backend python -m app.main --text "open System Settings" --dry-run
PYTHONPATH=backend python -m app.main --inspect-ui
PYTHONPATH=backend python -m app.main --voice --dry-run
PYTHONPATH=backend python -m app.main --wake-word --dry-run
```

Remove `--dry-run` only when you want Charlie to control macOS. The current commands
are `open Chrome`, `open Safari`, `open VS Code`, `go to YouTube`, `search Google for
Python tutorials`, `type hello world`, `press enter`, `scroll down`, `scroll up`,
`increase volume`, `decrease volume`, `mute`, `take a screenshot`, `lock my Mac`,
`turn on dark mode`, `turn off dark mode`, and `switch to Chrome`.
Phase 3 also supports `open Accessibility settings`, `open Display settings`, `open Sound
settings`, `open Bluetooth settings`, `open Wi-Fi settings`, and `open Privacy & Security
settings`, plus compound commands such as `open VS Code and open LeetCode`.

`--inspect-ui` prints the frontmost application's accessibility tree. Accessibility
commands match exact or unique partial values from `AXTitle`, `AXDescription`,
`AXIdentifier`, and `AXRoleDescription`; ambiguous matches fail closed. Supported
actions include `ACCESSIBILITY_CLICK`, `ACCESSIBILITY_SELECT`, `ACCESSIBILITY_FOCUS`,
`ACCESSIBILITY_READ_FOCUSED`, and `ACCESSIBILITY_INSPECT`.

Grant the terminal or launcher running Charlie macOS Accessibility permission in
System Settings -> Privacy & Security -> Accessibility. Charlie never uses screenshots,
coordinates, or model-generated shell commands for these operations.

## Local voice setup

Charlie does not download whisper.cpp or speech models automatically. Install the
official whisper.cpp project separately:

```bash
git clone https://github.com/ggml-org/whisper.cpp.git
cd whisper.cpp
cmake -B build
cmake --build build -j --config Release
./models/download-ggml-model.sh base.en
```

Add the resulting paths to the repository root `.env`:

```dotenv
CHARLIE_WHISPER_BIN=/absolute/path/to/whisper.cpp/build/bin/whisper-cli
CHARLIE_WHISPER_MODEL=/absolute/path/to/whisper.cpp/models/ggml-base.en.bin
CHARLIE_RECORD_SECONDS=5
CHARLIE_MAX_RECORD_SECONDS=5
CHARLIE_MIN_RECORD_SECONDS=0.5
CHARLIE_SILENCE_SECONDS=0.7
CHARLIE_SPEECH_THRESHOLD=0.015
CHARLIE_PREROLL_SECONDS=0.2
CHARLIE_SILENCE_DETECTION=1
CHARLIE_WAKE_CHUNK_SECONDS=2
CHARLIE_SAMPLE_RATE=16000
```

Relative model paths are resolved from the Charlie repository root, so this also
works when the model is copied to `models/ggml-base.en.bin`:

```dotenv
CHARLIE_WHISPER_MODEL=models/ggml-base.en.bin
```

Install the Python recording dependencies in Charlie's environment:

```bash
source .venv/bin/activate
uv pip install sounddevice soundfile
```

Grant Terminal, VS Code, or the launcher running Charlie access under
`System Settings -> Privacy & Security -> Microphone`.

Run one command and exit:

```bash
PYTHONPATH=backend python -m app.main --voice
PYTHONPATH=backend python -m app.main --voice --dry-run
PYTHONPATH=backend python -m app.main --wake-word
PYTHONPATH=backend python -m app.main --wake-word --dry-run
```

Voice mode records one command using local speech/silence detection, runs whisper.cpp
locally, and sends only the resulting text transcript to Jev. It prints recording,
Whisper, decision, execution, and total timing. Set `CHARLIE_SILENCE_DETECTION=0`
to use the fixed maximum duration fallback.

Wake-word mode starts in `WAITING_FOR_WAKE_WORD`, listens in short local chunks for
`CHARLIE_WAKE_WORD` (default `Charlie`), then records and processes one command before
returning to the waiting state. `Charlie, open Chrome` is also accepted; only `open
Chrome` is sent to Jev.

Example timing output:

```text
Voice timing:
	Recording:     1.20s
	Whisper:       0.72s
	Decision:      0.65s
	Execution:     0.08s
	Total:         2.65s
```

Troubleshooting:

- `Whisper executable not found`: set `CHARLIE_WHISPER_BIN` to the executable path.
- `Whisper model not found`: set `CHARLIE_WHISPER_MODEL` to `ggml-base.en.bin`.
- `No default microphone was found`: select an input device in macOS Sound settings.
- `Microphone permission denied`: grant the launching application Microphone access.
- `No speech detected`: increase `CHARLIE_RECORD_SECONDS` or speak closer to the microphone.

Run tests and lint:

```bash
PYTHONPATH=backend python -m pytest backend/tests -q
uvx ruff check backend
```