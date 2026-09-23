from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

from app import config
from app.actions.accessibility import AccessibilityError, AccessibilityInspector
from app.actions.executor import ActionExecutor
from app.actions.macos import NativeMacOSExecutor, installed_applications
from app.actions.schema import DecisionContext
from app.audio.microphone import Microphone, MicrophoneError, SoundDeviceMicrophone
from app.audio.stt import SpeechToText, SpeechToTextError, WhisperSTT
from app.brain.jev import JevDecisionEngine
from app.commands.compound import split_compound


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Charlie macOS voice-control assistant")
    parser.add_argument("--text", help="Use text instead of microphone input")
    parser.add_argument("--dry-run", action="store_true", help="Decide but do not control macOS")
    parser.add_argument("--inspect-ui", action="store_true", help="Print the frontmost app's accessibility tree")
    parser.add_argument("--voice", action="store_true", help="Record one local command and transcribe it with whisper.cpp")
    return parser


def run_text(transcript: str, dry_run: bool = False) -> int:
    if not transcript.strip():
        print("No speech detected.")
        return 1
    engine = JevDecisionEngine()
    executor = ActionExecutor(NativeMacOSExecutor())
    steps = split_compound(transcript)
    for index, step in enumerate(steps, start=1):
        accessible_targets: list[str] = []
        try:
            accessible_targets = AccessibilityInspector().target_names()
        except AccessibilityError:
            pass
        context = DecisionContext(
            transcript=step,
            installed_apps=installed_applications(),
            accessible_targets=accessible_targets,
        )
        action = engine.decide(step, context)
        result = executor.execute(action, dry_run=dry_run)
        prefix = f"Step {index}:\n" if len(steps) > 1 else ""
        print(f"{prefix}Transcript:\n{step}\n\nAction:\n{action.action.value}\n\nTarget:\n{action.target or '-'}\n\nExecution:\n{result}")
    return 0


def run_voice(
    dry_run: bool = False,
    microphone: Microphone | None = None,
    stt: SpeechToText | None = None,
    run_transcript: Callable[[str, bool], int] | None = None,
) -> int:
    """Record one local clip, transcribe it, then use the normal text pipeline."""
    audio_path: Path | None = None
    try:
        microphone = microphone or SoundDeviceMicrophone(config.CHARLIE_RECORD_SECONDS, config.CHARLIE_SAMPLE_RATE)
        stt = stt or WhisperSTT()
        print("Listening...")
        audio_path = microphone.record()
        transcript = stt.transcribe(audio_path)
        if not transcript.strip():
            print("No speech detected.")
            return 1
        print(f"Transcript: {transcript}")
        runner = run_transcript or run_text
        return runner(transcript, dry_run)
    except (MicrophoneError, SpeechToTextError) as error:
        print(str(error))
        return 1
    finally:
        if audio_path is not None:
            audio_path.unlink(missing_ok=True)


def main() -> int:
    args = build_parser().parse_args()
    if args.inspect_ui:
        print(AccessibilityInspector().render())
        return 0
    if args.voice:
        return run_voice(dry_run=args.dry_run)
    if not args.text:
        raise SystemExit("Provide --text, --voice, or --inspect-ui")
    return run_text(args.text, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
