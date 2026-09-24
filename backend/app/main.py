from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
from time import perf_counter

from app import config
from app.actions.accessibility import AccessibilityError, AccessibilityInspector
from app.actions.executor import ActionExecutor
from app.actions.macos import NativeMacOSExecutor, installed_applications
from app.actions.schema import DecisionContext
from app.audio.microphone import Microphone, MicrophoneError, SoundDeviceMicrophone
from app.audio.stt import SpeechToText, SpeechToTextError, WhisperSTT
from app.audio.timing import TimingContext, VoiceTiming
from app.audio.wake_word import WakeWordDetector, WhisperWakeWordDetector
from app.brain.jev import JevDecisionEngine
from app.commands.compound import split_compound
from app.voice_state import VoiceStateMachine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Charlie macOS voice-control assistant")
    parser.add_argument("--text", help="Use text instead of microphone input")
    parser.add_argument("--dry-run", action="store_true", help="Decide but do not control macOS")
    parser.add_argument("--inspect-ui", action="store_true", help="Print the frontmost app's accessibility tree")
    parser.add_argument("--voice", action="store_true", help="Record one local command and transcribe it with whisper.cpp")
    parser.add_argument("--wake-word", action="store_true", help="Wait for the local wake word before recording a command")
    return parser


def run_text(transcript: str, dry_run: bool = False, timing: VoiceTiming | None = None) -> int:
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
        if timing:
            timing.mark("decision_start")
        try:
            action = engine.decide(step, context)
            if timing:
                timing.mark("decision_end")
                timing.mark("executor_start")
            result = executor.execute(action, dry_run=dry_run)
        except Exception as error:  # noqa: BLE001
            print(f"Step {index} failed: {error}")
            if len(steps) > 1:
                print("Compound command aborted.")
            return 1
        if timing:
            timing.mark("executor_end")
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
    with TimingContext() as timing:
        audio_path: Path | None = None
        try:
            microphone = microphone or SoundDeviceMicrophone()
            stt = stt or WhisperSTT()
            print("Listening...")
            timing.mark("recording_start")
            audio_path = microphone.record()
            timing.mark("recording_end")
            timing.mark("audio_file_created")
            timing.mark("whisper_start")
            transcript = stt.transcribe(audio_path)
            timing.mark("whisper_end")
            timing.mark("transcript_available")
            if not transcript.strip():
                print("No speech detected.")
                return 1
            print(f"Transcript: {transcript}")
            runner = run_transcript or (lambda text, dry: run_text(text, dry, timing))
            result = runner(transcript, dry_run)
            timing.mark("total_end")
            print(timing.summary())
            return result
        except (MicrophoneError, SpeechToTextError) as error:
            print(str(error))
            timing.mark("total_end")
            print(timing.summary())
            return 1
        finally:
            if audio_path is not None:
                audio_path.unlink(missing_ok=True)


def run_wake_word(
    dry_run: bool = False,
    microphone: Microphone | None = None,
    stt: SpeechToText | None = None,
    detector: WakeWordDetector | None = None,
    command_microphone: Microphone | None = None,
    run_transcript: Callable[[str, bool], int] | None = None,
    max_cycles: int | None = None,
) -> int:
    """Wait for the local wake word, then process one command at a time."""
    detector = detector or WhisperWakeWordDetector(config.WAKE_WORD)
    microphone = microphone or SoundDeviceMicrophone(config.CHARLIE_WAKE_CHUNK_SECONDS)
    stt = stt or WhisperSTT()
    states = VoiceStateMachine()
    states.start_waiting()
    cycles = 0
    print(f'Waiting for "{config.WAKE_WORD}"...')
    while max_cycles is None or cycles < max_cycles:
        cycles += 1
        audio_path: Path | None = None
        try:
            wake_start = perf_counter()
            audio_path = microphone.record()
            transcript = stt.transcribe(audio_path)
            match = detector.match(transcript)
            wake_elapsed = perf_counter() - wake_start
        except (MicrophoneError, SpeechToTextError) as error:
            if max_cycles is not None:
                print(str(error))
            continue
        finally:
            if audio_path is not None:
                audio_path.unlink(missing_ok=True)

        if not match.detected:
            continue
        print(f"Wake detection: {wake_elapsed:.2f}s")
        states.wake_detected()
        command = match.command
        if not command:
            command_input = command_microphone or SoundDeviceMicrophone()

            def command_runner(transcript: str, dry: bool) -> int:
                repeated_wake = detector.match(transcript)
                if repeated_wake.detected:
                    if repeated_wake.command:
                        target = run_transcript or run_text
                        return target(repeated_wake.command, dry)
                    print("Wake word heard; waiting for a command.")
                    return 1
                target = run_transcript or run_text
                return target(transcript, dry)

            command_result = run_voice(dry_run, command_input, stt, command_runner)
            if command_result == 0:
                states.command_received()
                states.execution_started()
        else:
            states.command_received()
            states.execution_started()
            command_result = run_text(command, dry_run) if run_transcript is None else run_transcript(command, dry_run)
        states.reset()
        print(f'Waiting for "{config.WAKE_WORD}"...')
        if command_result != 0:
            continue
    return 0


def main() -> int:
    args = build_parser().parse_args()
    if args.inspect_ui:
        print(AccessibilityInspector().render())
        return 0
    if args.voice:
        return run_voice(dry_run=args.dry_run)
    if args.wake_word:
        return run_wake_word(dry_run=args.dry_run)
    if not args.text:
        raise SystemExit("Provide --text, --voice, --wake-word, or --inspect-ui")
    return run_text(args.text, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
