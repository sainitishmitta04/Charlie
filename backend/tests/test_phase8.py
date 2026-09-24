from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from app.actions.macos import NativeMacOSExecutor
from app.actions.schema import Action
from app.brain.jev import JevDecisionEngine
from app.context import SessionContext, TaskState
from app.main import (
    _context_action,
    _conversation_transcript,
    run_text,
    run_text_sequence,
    run_wake_word,
)
from app.voice_state import VoiceState, VoiceStateMachine


def test_empty_context_and_clear():
    context = SessionContext()
    assert context.as_dict() == {}


def test_context_timeout_is_in_memory_only(monkeypatch):
    context = SessionContext(current_app="Notes")
    monkeypatch.setattr("app.context.monotonic", lambda: context.last_activity + 301)
    assert context.expired(300)
    context.current_app = "Notes"
    context.last_target = "milk"
    context.clear()
    assert context.as_dict() == {}


def test_context_updates_after_successful_actions():
    context = SessionContext()
    context.update_from_action(Action(action="OPEN_APP", target="Google Chrome"))
    assert context.current_app == "Google Chrome"
    context.update_from_action(Action(action="OPEN_URL", url="https://youtube.com"))
    assert context.current_url == "https://youtube.com"
    context.update_from_action(Action(action="SEARCH_WEB", query="Python tutorials"))
    assert context.last_action == "SEARCH_WEB"
    assert context.last_target == "Python tutorials"


def test_context_tracks_previous_app_and_close():
    context = SessionContext(current_app="Finder")
    context.update_from_action(Action(action="SWITCH_APP", target="Google Chrome"))
    assert context.previous_app == "Finder"
    assert context.current_app == "Google Chrome"
    context.update_from_action(Action(action="QUIT_APP", target="Google Chrome"))
    assert context.current_app is None
    assert context.previous_app == "Google Chrome"


def test_failed_action_does_not_update_context():
    context = SessionContext(current_app="Finder")
    before = context.as_dict()
    executor = Mock(side_effect=ValueError("failed"))
    with pytest.raises(ValueError):
        executor(Action(action="OPEN_APP", target="Notion"))
    assert context.as_dict() == before


def test_deterministic_follow_up_resolution():
    context = SessionContext(current_app="Google Chrome", current_url="https://youtube.com")
    action, reason = _context_action("go there", context)
    assert reason is None
    assert action == Action(action="OPEN_URL", url="https://youtube.com")
    context.previous_app = "Finder"
    action, reason = _context_action("switch back", context)
    assert reason is None
    assert action == Action(action="SWITCH_APP", target="Finder")


def test_missing_and_ambiguous_references_are_rejected():
    action, reason = _context_action("go there", SessionContext())
    assert action is None and "No URL" not in (reason or "")
    context = SessionContext(current_app="Chrome", previous_app="Finder")
    action, reason = _context_action("open it", context)
    assert action is None and "Ambiguous" in (reason or "")


def test_notes_follow_up_becomes_type_text():
    action, reason = _context_action("add milk", SessionContext(current_app="Notes"))
    assert reason is None
    assert action == Action(action="TYPE_TEXT", text="milk")


def test_clear_commands_are_resolved_before_jev(monkeypatch):
    monkeypatch.setattr("app.actions.macos.installed_applications", lambda: ["Google Chrome", "Notes"])
    action, reason = _context_action("open Chrome", SessionContext())
    assert reason is None and action == Action(action="OPEN_APP", target="Google Chrome")
    action, reason = _context_action("go to YouTube", SessionContext())
    assert reason is None and action == Action(action="OPEN_URL", url="https://www.youtube.com")
    action, reason = _context_action("write buy milk", SessionContext())
    assert reason is None and action == Action(action="TYPE_TEXT", text="buy milk")


def test_task_state_progress_and_completion():
    task = TaskState.start([Action(action="OPEN_APP", target="Chrome"), Action(action="OPEN_URL", url="https://youtube.com")])
    task.complete(Action(action="OPEN_APP", target="Chrome"))
    assert task.status == "ACTIVE"
    task.complete(Action(action="OPEN_URL", url="https://youtube.com"))
    assert task.status == "COMPLETED"
    assert task.completed_steps == ["OPEN_APP", "OPEN_URL"]


def test_text_sequence_reuses_context(monkeypatch):
    actions = iter([
        Action(action="OPEN_APP", target="Google Chrome"),
        Action(action="OPEN_URL", url="https://www.youtube.com"),
    ])

    class FakeEngine:
        def decide(self, transcript, context):
            assert context.session_context.get("current_app") == "Google Chrome" if transcript.startswith("go") else True
            return next(actions)

    monkeypatch.setattr("app.main.JevDecisionEngine", lambda: FakeEngine())
    monkeypatch.setattr("app.main.ActionExecutor", lambda macos: Mock(execute=lambda action, dry_run=False: "ok"))
    monkeypatch.setattr("app.main.AccessibilityInspector", lambda: Mock(target_names=list))
    assert run_text_sequence(["open Chrome", "go to YouTube"], dry_run=True) == 0


def test_search_query_removes_command_words():
    response = {"answers": {"action": {"choice": "SEARCH_WEB"}, "engine": {"choice": "google"}}}
    action = JevDecisionEngine._parse_response(response, "search for Python tutorials", [])
    assert action.query == "Python tutorials"


def test_youtube_context_resolves_current_site_search():
    context = SessionContext(current_url="https://www.youtube.com")
    action, reason = _context_action("search for Python tutorials", context)
    assert reason is None
    assert action == Action(action="SEARCH_CURRENT_SITE", query="Python tutorials", url="https://www.youtube.com")


def test_explicit_web_search_does_not_use_current_site():
    context = SessionContext(current_url="https://www.youtube.com")
    action, reason = _context_action("search the web for Python tutorials", context)
    assert reason is None
    assert action == Action(action="SEARCH_WEB", query="Python tutorials", engine="google")


def test_search_here_without_supported_site_is_safe():
    action, reason = _context_action("search here for Python tutorials", SessionContext(current_url="https://example.com"))
    assert action is None
    assert "supported current site" in reason


def test_youtube_search_url_is_encoded(monkeypatch):
    commands = []
    monkeypatch.setattr(NativeMacOSExecutor, "_run", staticmethod(lambda command: commands.append(command)))
    action = Action(action="SEARCH_CURRENT_SITE", query="Python tutorials", url="https://www.youtube.com")
    NativeMacOSExecutor().execute("SEARCH_CURRENT_SITE", action)
    assert commands == [["open", "https://www.youtube.com/results?search_query=Python+tutorials"]]


@pytest.mark.parametrize("transcript,key", [("Enter", "ENTER"), ("press Enter", "ENTER"), ("hit return", "RETURN")])
def test_enter_variants_are_press_key_actions(transcript, key):
    action, reason = _context_action(transcript, SessionContext())
    assert reason is None
    assert action == Action(action="PRESS_KEY", key=key)


@pytest.mark.parametrize(
    ("transcript", "key"),
    [
        ("Enter", "ENTER"),
        ("Enter.", "ENTER"),
        ("ENTER!", "ENTER"),
        ("enter?", "ENTER"),
        ("press enter", "ENTER"),
        ("press Enter.", "ENTER"),
        ("hit enter", "ENTER"),
        ("return", "RETURN"),
        ("press return", "RETURN"),
        ("hit return", "RETURN"),
        ("next line", "ENTER"),
        ("next line.", "ENTER"),
        ("new line", "ENTER"),
        ("tab", "TAB"),
        ("press tab", "TAB"),
        ("hit tab", "TAB"),
        ("backspace", "BACKSPACE"),
        ("delete", "DELETE"),
        ("escape", "ESCAPE"),
        ("arrow up", "UP"),
        ("press up arrow", "UP"),
        ("press arrow down", "DOWN"),
        ("arrow left", "LEFT"),
        ("press right arrow", "RIGHT"),
    ],
)
def test_exact_voice_key_commands_are_deterministic(transcript, key):
    action, reason = _context_action(transcript, SessionContext())
    assert reason is None
    assert action == Action(action="PRESS_KEY", key=key)


@pytest.mark.parametrize(
    "transcript",
    [
        "enter the grocery list",
        "right, grocery list",
        "right arrow",
        "delete the previous item",
        "press enter command",
    ],
)
def test_non_exact_key_phrases_are_not_deterministic_key_commands(transcript):
    action, _ = _context_action(transcript, SessionContext())
    assert action is None or action.action != "PRESS_KEY"


def test_notes_text_preserves_original_punctuation_and_case(monkeypatch, capsys):
    actions = []
    monkeypatch.setattr("app.main.JevDecisionEngine", lambda: pytest.fail("Jev should not be initialized"))
    monkeypatch.setattr("app.main.ActionExecutor", lambda macos: SimpleNamespace(execute=lambda action, dry_run=False: actions.append(action) or "ok"))
    monkeypatch.setattr("app.main.AccessibilityInspector", lambda: SimpleNamespace(target_names=list))
    monkeypatch.setattr("app.main.installed_applications", list)

    assert run_text("Hello, world!", dry_run=True, session=SessionContext(current_app="Notes")) == 0
    assert actions == [Action(action="TYPE_TEXT", text="Hello, world!")]
    assert "Target:\nHello, world!" in capsys.readouterr().out


def test_notes_conversation_list_uses_explicit_enter_without_skipping_numbers(monkeypatch):
    actions = []
    monkeypatch.setattr("app.main.JevDecisionEngine", lambda: pytest.fail("Jev should not be initialized"))
    monkeypatch.setattr("app.main.ActionExecutor", lambda macos: SimpleNamespace(execute=lambda action, dry_run=False: actions.append(action) or "ok"))
    monkeypatch.setattr("app.main.AccessibilityInspector", lambda: SimpleNamespace(target_names=list))
    monkeypatch.setattr("app.main.installed_applications", list)
    session = SessionContext(current_app="Notes")

    for transcript in ("Grocery List", "Enter.", "make a numbered list", "Eggs", "Enter", "Milk"):
        assert run_text(transcript, dry_run=True, session=session) == 0

    assert actions == [
        Action(action="TYPE_TEXT", text="Grocery List"),
        Action(action="PRESS_KEY", key="ENTER"),
        Action(action="TYPE_TEXT", text="1. Eggs"),
        Action(action="PRESS_KEY", key="ENTER"),
        Action(action="TYPE_TEXT", text="2. Milk"),
    ]


@pytest.mark.parametrize(
    ("transcript", "expected"),
    [
        ("right, grocery list?", "grocery list?"),
        ("okay, grocery list", "grocery list"),
        ("ok, grocery list", "grocery list"),
        ("alright, grocery list", "grocery list"),
        ("right arrow", "right arrow"),
        ("right click", "right click"),
    ],
)
def test_conversation_filler_removal_is_conservative(transcript, expected):
    assert _conversation_transcript(transcript) == expected


def test_list_mode_numbers_items_and_resets():
    context = SessionContext(current_app="Notes")
    action, message = _context_action("make a numbered list", context)
    assert action is None and message == "Numbered list mode enabled."
    action, _ = _context_action("add eggs", context)
    assert action.text == "1. eggs"
    context.next_list_item()
    action, _ = _context_action("add milk", context)
    assert action.text == "2. milk"
    context.clear()
    assert context.list_number == 1 and not context.list_mode


def test_conversation_state_machine_supports_active_follow_ups():
    machine = VoiceStateMachine()
    machine.start_waiting()
    machine.wake_detected()
    machine.command_received()
    machine.execution_started()
    machine.conversation_started()
    assert machine.state == VoiceState.CONVERSATION_ACTIVE
    machine.follow_up_started()
    machine.command_received()
    machine.execution_started()
    machine.conversation_started()
    assert machine.state == VoiceState.CONVERSATION_ACTIVE
    machine.conversation_ended()
    assert machine.state == VoiceState.WAITING_FOR_WAKE_WORD


def test_failed_follow_up_returns_to_active_conversation():
    machine = VoiceStateMachine()
    machine.start_waiting()
    machine.wake_detected()
    machine.command_received()
    machine.execution_started()
    machine.conversation_started()
    machine.follow_up_started()
    machine.follow_up_failed()
    assert machine.state == VoiceState.CONVERSATION_ACTIVE


def test_wake_mode_processes_follow_up_without_wake_word(tmp_path):
    wake_audio = tmp_path / "wake.wav"
    command_audio = tmp_path / "command.wav"
    wake_audio.write_bytes(b"wake")
    command_audio.write_bytes(b"command")
    transcripts = iter(["Charlie, open Notes", "Grocery List"])
    calls = []
    result = run_wake_word(
        dry_run=True,
        microphone=SimpleNamespace(record=lambda: wake_audio),
        command_microphone=SimpleNamespace(record=lambda: command_audio),
        stt=SimpleNamespace(transcribe=lambda _: next(transcripts)),
        run_transcript=lambda transcript, dry: calls.append((transcript, dry)) or 0,
        max_cycles=2,
    )
    assert result == 0
    assert calls == [("open Notes", True), ("Grocery List", True)]


@pytest.mark.parametrize("stop_text", ["stop", "stop listening", "that's all", "done"])
def test_conversation_stop_commands_never_reach_pipeline(tmp_path, stop_text):
    wake_audio = tmp_path / "wake.wav"
    command_audio = tmp_path / "command.wav"
    wake_audio.write_bytes(b"wake")
    command_audio.write_bytes(b"command")
    calls = []
    transcripts = iter(["Charlie, open Notes", stop_text])
    result = run_wake_word(
        dry_run=True,
        microphone=SimpleNamespace(record=lambda: wake_audio),
        command_microphone=SimpleNamespace(record=lambda: command_audio),
        stt=SimpleNamespace(transcribe=lambda _: next(transcripts)),
        run_transcript=lambda transcript, dry: calls.append(transcript) or 0,
        max_cycles=2,
    )
    assert result == 0
    assert calls == ["open Notes"]


def test_wake_word_inside_active_conversation_is_stripped(tmp_path):
    wake_audio = tmp_path / "wake.wav"
    command_audio = tmp_path / "command.wav"
    wake_audio.write_bytes(b"wake")
    command_audio.write_bytes(b"command")
    transcripts = iter(["Charlie, open Chrome", "Charlie, go to YouTube"])
    calls = []
    run_wake_word(
        dry_run=True,
        microphone=SimpleNamespace(record=lambda: wake_audio),
        command_microphone=SimpleNamespace(record=lambda: command_audio),
        stt=SimpleNamespace(transcribe=lambda _: next(transcripts)),
        run_transcript=lambda transcript, dry: calls.append(transcript) or 0,
        max_cycles=2,
    )
    assert calls == ["open Chrome", "go to YouTube"]
