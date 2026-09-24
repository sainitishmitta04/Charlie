from __future__ import annotations

import argparse
import re
from collections.abc import Callable
from pathlib import Path
from time import perf_counter

from app import config
from app.actions.accessibility import AccessibilityError, AccessibilityInspector
from app.actions.executor import ActionExecutor
from app.actions.macos import (
    NativeMacOSExecutor,
    installed_applications,
    resolve_application,
)
from app.actions.schema import Action, ActionType, DecisionContext
from app.audio.microphone import Microphone, MicrophoneError, SoundDeviceMicrophone
from app.audio.stt import SpeechToText, SpeechToTextError, WhisperSTT
from app.audio.timing import TimingContext, VoiceTiming
from app.audio.wake_word import WakeWordDetector, WhisperWakeWordDetector
from app.brain.jev import JevDecisionEngine
from app.commands.compound import split_compound
from app.commands.normalize import (
    deterministic_key_command,
    normalize_stop_command,
    normalize_voice_command,
)
from app.context import SessionContext, TaskState
from app.voice_state import VoiceState, VoiceStateMachine

_CONVERSATION_STOP_COMMANDS = {"stop", "stop listening", "thats all", "done"}


def _conversation_transcript(transcript: str) -> str:
    """Remove only obvious filler at the start of an active follow-up."""
    cleaned = " ".join(transcript.strip().split())
    lowered = cleaned.casefold()
    for filler in ("right, ", "okay, ", "ok, ", "alright, "):
        if lowered.startswith(filler) and not lowered.startswith("right arrow") and not lowered.startswith("right click"):
            return cleaned[len(filler):].strip()
    return cleaned


def _is_conversation_stop(transcript: str) -> bool:
    return normalize_stop_command(transcript) in _CONVERSATION_STOP_COMMANDS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Charlie macOS voice-control assistant")
    parser.add_argument("--text", help="Use text instead of microphone input")
    parser.add_argument("--text-sequence", nargs="+", help="Run multiple text commands in one session")
    parser.add_argument("--dry-run", action="store_true", help="Decide but do not control macOS")
    parser.add_argument("--inspect-ui", action="store_true", help="Print the frontmost app's accessibility tree")
    parser.add_argument("--voice", action="store_true", help="Record one local command and transcribe it with whisper.cpp")
    parser.add_argument("--wake-word", action="store_true", help="Wait for the local wake word before recording a command")
    return parser


def _context_action(transcript: str, session: SessionContext) -> tuple[object | None, str | None]:
    normalized = normalize_voice_command(transcript)
    if normalized in {"reset", "forget what we were doing", "forget what we are doing"}:
        session.clear()
        return None, "Context reset."
    if normalized in {"make a numbered list", "add a list", "new list", "start a new list"}:
        session.start_numbered_list()
        return None, "Numbered list mode enabled."
    key = deterministic_key_command(transcript)
    if key is not None:
        return Action(action=ActionType.PRESS_KEY, key=key), None
    if normalized in {"switch back", "go back to the previous app"}:
        if not session.previous_app:
            return None, "Which app do you mean? No previous app is known."
        return Action(action=ActionType.SWITCH_APP, target=session.previous_app), None
    if normalized in {"go there", "open it", "open that"}:
        if normalized == "go there" and session.current_url:
            return Action(action=ActionType.OPEN_URL, url=session.current_url), None
        if normalized != "go there" and session.current_app and not session.previous_app:
            return Action(action=ActionType.OPEN_APP, target=session.current_app), None
        return None, f"Ambiguous reference: {transcript!r}."
    if session.current_app == "Notes" and session.list_mode:
        match = re.match(r"(?:add\s+)?(.+)$", transcript.strip(), re.IGNORECASE)
        if match:
            return Action(action=ActionType.TYPE_TEXT, text=f"{session.list_number}. {match.group(1).strip()}"), None
    if session.current_app == "Notes":
        match = re.match(r"(?:add|write|type)\s+(.+)$", transcript.strip(), re.IGNORECASE)
        if match:
            return Action(action=ActionType.TYPE_TEXT, text=match.group(1).strip()), None
        if transcript.strip():
            return Action(action=ActionType.TYPE_TEXT, text=transcript.strip()), None
    app_match = re.match(r"(?:open|launch|switch to)\s+(.+)$", transcript.strip(), re.IGNORECASE)
    if app_match:
        requested = app_match.group(1).strip().rstrip(".")
        try:
            app = resolve_application(requested)
        except ValueError:
            app = None
        if app is not None:
            action_type = ActionType.SWITCH_APP if transcript.casefold().startswith("switch to") else ActionType.OPEN_APP
            return Action(action=action_type, target=app), None
    url_match = re.match(r"(?:go to|open)\s+(youtube|google|leetcode|github)(?:\.com)?\s*$", transcript.strip(), re.IGNORECASE)
    if url_match:
        urls = {
            "youtube": "https://www.youtube.com", "google": "https://www.google.com",
            "leetcode": "https://leetcode.com", "github": "https://github.com",
        }
        return Action(action=ActionType.OPEN_URL, url=urls[url_match.group(1).casefold()]), None
    search_match = re.match(r"(?:search|google|look up|find)(?:\s+(?:the\s+)?web)?(?:\s+on\s+\w+)?\s+(?:for\s+)?(.+)$", transcript.strip(), re.IGNORECASE)
    if search_match:
        query = search_match.group(1).strip().rstrip(".")
        if re.search(r"\b(?:here|this site|this website)\b", normalized):
            if session.current_url and "youtube.com" in session.current_url.casefold():
                return Action(action=ActionType.SEARCH_CURRENT_SITE, query=query, url=session.current_url), None
            return None, "I do not know a supported current site to search."
        if session.current_url and "youtube.com" in session.current_url.casefold() and not re.search(r"\b(?:web|google)\b", normalized):
            return Action(action=ActionType.SEARCH_CURRENT_SITE, query=query, url=session.current_url), None
        return Action(action=ActionType.SEARCH_WEB, query=query, engine="google"), None
    text_match = re.match(r"(?:type|write|enter)\s+(.+)$", transcript.strip(), re.IGNORECASE)
    if text_match:
        return Action(action=ActionType.TYPE_TEXT, text=text_match.group(1).strip()), None
    return None, None


def run_text(
    transcript: str,
    dry_run: bool = False,
    timing: VoiceTiming | None = None,
    session: SessionContext | None = None,
) -> int:
    if not transcript.strip():
        print("No speech detected.")
        return 1
    session = session or SessionContext()
    if session.expired(config.CHARLIE_CONTEXT_TIMEOUT_SECONDS):
        session.clear()
    context_before = session.as_dict()
    direct_action, message = _context_action(transcript, session)
    if message and direct_action is None:
        print(f"Transcript:\n{transcript}\n\nContext:\n{context_before}\n\nDecision:\nWAIT\n\nReason:\n{message}")
        return 0 if message in {"Context reset.", "Numbered list mode enabled."} else 1
    engine: JevDecisionEngine | None = None
    executor = ActionExecutor(NativeMacOSExecutor())
    steps = split_compound(transcript)
    if len(steps) > 1:
        session.active_task = TaskState()
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
            session_context=session.as_dict(),
        )
        if timing:
            timing.mark("decision_start")
        try:
            step_action, step_message = _context_action(step, session)
            if step_message and step_action is None:
                raise ValueError(step_message)
            action = step_action or (direct_action if direct_action is not None and len(steps) == 1 else None)
            if action is None:
                if engine is None:
                    engine = JevDecisionEngine()
                action = engine.decide(step, context)
            if timing:
                timing.mark("decision_end")
                timing.mark("executor_start")
            if action.action == ActionType.TYPE_TEXT and session.list_mode and session.list_number > 1 and session.last_action != ActionType.PRESS_KEY.value:
                executor.execute(Action(action=ActionType.PRESS_KEY, key="ENTER"), dry_run=dry_run)
            result = executor.execute(action, dry_run=dry_run)
        except Exception as error:  # noqa: BLE001
            session.fail_task()
            print(f"Step {index} failed: {error}")
            if len(steps) > 1:
                print("Compound command aborted.")
            return 1
        if timing:
            timing.mark("executor_end")
        if session.active_task is not None and len(steps) > 1 and len(session.active_task.steps) < index:
            session.active_task.steps.append(action.action.value)
        session.update_from_action(action)
        if action.action == ActionType.TYPE_TEXT and session.list_mode:
            session.next_list_item()
        prefix = f"Step {index}:\n" if len(steps) > 1 else ""
        display_target = action.query if action.action in {ActionType.SEARCH_WEB, ActionType.SEARCH_CURRENT_SITE} else (
            action.target or action.url or action.text or action.key or "-"
        )
        print(
            f"{prefix}Transcript:\n{step}\n\nContext before:\n{context_before}\n\n"
            f"Action:\n{action.action.value}\n\nTarget:\n{display_target}\n\n"
            f"Execution:\n{result}\n\nContext after:\n{session.as_dict()}"
        )
        context_before = session.as_dict()
    if session.active_task is not None and len(steps) > 1:
        session.active_task.status = "COMPLETED"
    return 0


def run_text_sequence(transcripts: list[str], dry_run: bool = False) -> int:
    session = SessionContext()
    for transcript in transcripts:
        result = run_text(transcript, dry_run=dry_run, session=session)
        if result != 0:
            return result
    return 0


def run_voice(
    dry_run: bool = False,
    microphone: Microphone | None = None,
    stt: SpeechToText | None = None,
    run_transcript: Callable[[str, bool], int] | None = None,
    session: SessionContext | None = None,
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
            runner = run_transcript or (lambda text, dry: run_text(text, dry, timing, session))
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
    session: SessionContext | None = None,
) -> int:
    """Wait for a wake word, then keep a short-lived conversational command window."""
    detector = detector or WhisperWakeWordDetector(config.WAKE_WORD)
    microphone = microphone or SoundDeviceMicrophone(config.CHARLIE_WAKE_CHUNK_SECONDS)
    stt = stt or WhisperSTT()
    states = VoiceStateMachine()
    session = session or SessionContext()
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

            def first_command_runner(transcript: str, dry: bool) -> int:
                repeated_wake = detector.match(transcript)
                if repeated_wake.detected:
                    if repeated_wake.command:
                        target = run_transcript or run_text
                        return run_text(repeated_wake.command, dry, session=session) if run_transcript is None else target(repeated_wake.command, dry)
                    print("Wake word heard; waiting for a command.")
                    return 1
                target = run_transcript or run_text
                return run_text(transcript, dry, session=session) if run_transcript is None else target(transcript, dry)

            command_result = run_voice(dry_run, command_input, stt, first_command_runner, session)
        else:
            states.command_received()
            states.execution_started()
            command_result = run_text(command, dry_run, session=session) if run_transcript is None else run_transcript(command, dry_run)
        if command_result != 0:
            states.reset()
            print(f'Waiting for "{config.WAKE_WORD}"...')
            continue

        if states.state == VoiceState.LISTENING_FOR_COMMAND:
            states.command_received()
            states.execution_started()

        if states.state == VoiceState.EXECUTING:
            states.conversation_started()
        print("Conversation active.")
        conversation_started_at = perf_counter()
        ended_by_stop = False
        while (
            perf_counter() - conversation_started_at < config.CHARLIE_CONVERSATION_TIMEOUT_SECONDS
            and (max_cycles is None or cycles < max_cycles)
        ):
            cycles += 1
            states.follow_up_started()
            follow_up_started_at = perf_counter()
            conversation_ended = False

            def follow_up_runner(transcript: str, dry: bool) -> int:
                nonlocal conversation_ended
                repeated_wake = detector.match(transcript)
                if repeated_wake.detected:
                    transcript = repeated_wake.command
                    if not transcript:
                        print("Wake word heard; listening for a command.")
                        return 1
                transcript = _conversation_transcript(transcript)
                if not transcript.strip():
                    return 1
                if _is_conversation_stop(transcript):
                    conversation_ended = True
                    return 0
                target = run_transcript or run_text
                return run_text(transcript, dry, session=session) if run_transcript is None else target(transcript, dry)

            follow_up_result = run_voice(dry_run, command_microphone or SoundDeviceMicrophone(), stt, follow_up_runner, session)
            if conversation_ended:
                ended_by_stop = True
                states.conversation_ended()
                print("Conversation ended.")
                break
            if follow_up_result == 0:
                states.command_received()
                states.execution_started()
                states.conversation_started()
                conversation_started_at = perf_counter()
                continue
            states.follow_up_failed()
            if perf_counter() - follow_up_started_at >= config.CHARLIE_CONVERSATION_TIMEOUT_SECONDS:
                break
        else:
            pass
        if states.state == VoiceState.CONVERSATION_ACTIVE:
            states.conversation_ended()
        if not ended_by_stop:
            print("Conversation timeout.")
        print(f'Waiting for "{config.WAKE_WORD}"...')
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
    if args.text_sequence:
        return run_text_sequence(args.text_sequence, args.dry_run)
    if not args.text:
        raise SystemExit("Provide --text, --text-sequence, --voice, --wake-word, or --inspect-ui")
    return run_text(args.text, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
