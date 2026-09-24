import pytest
from app.actions.accessibility import AccessibilityInspector, AccessibilityNode
from app.actions.macos import NativeMacOSExecutor
from app.actions.schema import Action, ActionType
from app.brain.jev import JevDecisionEngine
from app.commands.compound import split_compound
from app.main import run_text


def test_phase_7_actions_validate():
    actions = [
        Action(action=ActionType.UNMUTE),
        Action(action=ActionType.OPEN_SYSTEM_SETTINGS),
        Action(action=ActionType.OPEN_ACCESSIBILITY_SETTINGS),
        Action(action=ActionType.OPEN_DISPLAY_SETTINGS),
        Action(action=ActionType.OPEN_SOUND_SETTINGS),
        Action(action=ActionType.OPEN_BLUETOOTH_SETTINGS),
        Action(action=ActionType.OPEN_WIFI_SETTINGS),
        Action(action=ActionType.OPEN_PRIVACY_SETTINGS),
        Action(action=ActionType.CLOSE_APP, target="Google Chrome"),
        Action(action=ActionType.QUIT_APP, target="Google Chrome"),
        Action(action=ActionType.PRESS_KEY, key="C", modifiers=["COMMAND"]),
    ]
    assert len(actions) == 11


def test_wait_and_text_validation():
    assert Action(action=ActionType.WAIT, seconds=0.1)
    with pytest.raises(ValueError, match="between 0.1 and 10"):
        Action(action=ActionType.WAIT, seconds=0.01)
    with pytest.raises(ValueError, match="non-empty"):
        Action(action=ActionType.TYPE_TEXT, text="")
    with pytest.raises(ValueError, match="supported"):
        Action(action=ActionType.PRESS_KEY, key="F13")


def test_jev_cannot_turn_unrelated_transcript_into_wait():
    response = {"answers": {"action": {"choice": "WAIT"}, "seconds": {"choice": "1"}}}
    with pytest.raises(ValueError, match="explicit wait"):
        JevDecisionEngine._parse_response(response, "wind howling", [])


def test_app_aliases_and_missing_apps(monkeypatch):
    monkeypatch.setattr("app.actions.macos.installed_applications", lambda: ["Google Chrome", "Finder"])
    assert NativeMacOSExecutor._resolve_app("chrome") == "Google Chrome"
    assert NativeMacOSExecutor._resolve_app("finder") == "Finder"
    with pytest.raises(ValueError, match="Notion is not installed"):
        NativeMacOSExecutor._resolve_app("Notion")


def test_app_lifecycle_and_system_settings_are_deterministic(monkeypatch):
    commands = []
    scripts = []
    monkeypatch.setattr(NativeMacOSExecutor, "_run", staticmethod(lambda command: commands.append(command)))
    monkeypatch.setattr(NativeMacOSExecutor, "_osascript", staticmethod(lambda script: scripts.append(script)))
    monkeypatch.setattr("app.actions.macos.installed_applications", lambda: ["Google Chrome"])
    executor = NativeMacOSExecutor()
    assert executor.execute("OPEN_APP", Action(action="OPEN_APP", target="chrome")) == "Opening Google Chrome."
    assert executor.execute("SWITCH_APP", Action(action="SWITCH_APP", target="chrome")) == "Switching to Google Chrome."
    assert executor.execute("CLOSE_APP", Action(action="CLOSE_APP", target="chrome")) == "Closed Google Chrome."
    assert executor.execute("QUIT_APP", Action(action="QUIT_APP", target="chrome")) == "Quit Google Chrome."
    assert executor.execute("OPEN_WIFI_SETTINGS", Action(action="OPEN_WIFI_SETTINGS")) == "Opening Wi Fi settings."
    assert commands[0] == ["open", "-a", "Google Chrome"]
    assert any("quit" in script for script in scripts)


def test_keyboard_shortcut_is_validated_and_deterministic(monkeypatch):
    scripts = []
    monkeypatch.setattr(NativeMacOSExecutor, "_osascript", staticmethod(lambda script: scripts.append(script)))
    result = NativeMacOSExecutor().execute("PRESS_KEY", Action(action="PRESS_KEY", key="C", modifiers=["COMMAND"]))
    assert result == "Pressed c."
    assert 'keystroke "c" using {command down}' in scripts[0]


def test_volume_unmute_and_scroll_dispatch(monkeypatch):
    scripts = []
    monkeypatch.setattr(NativeMacOSExecutor, "_osascript", staticmethod(lambda script: scripts.append(script)))
    executor = NativeMacOSExecutor()
    assert executor.execute("UNMUTE", Action(action="UNMUTE")) == "Volume unmuted."
    assert executor.execute("SCROLL", Action(action="SCROLL", direction="DOWN", amount=2)) == "Done."
    assert len(scripts) == 3


def test_url_and_search_are_validated_and_encoded(monkeypatch):
    commands = []
    monkeypatch.setattr(NativeMacOSExecutor, "_run", staticmethod(lambda command: commands.append(command)))
    executor = NativeMacOSExecutor()
    executor.execute("OPEN_URL", Action(action="OPEN_URL", url="https://github.com"))
    executor.execute("SEARCH_WEB", Action(action="SEARCH_WEB", query="Python decorators", engine="google"))
    assert commands == [
        ["open", "https://github.com"],
        ["open", "https://www.google.com/search?q=Python+decorators"],
    ]


def test_accessibility_role_filtering_prefers_compatible_nodes():
    button = AccessibilityNode("button", role="AXButton", title="Search")
    field = AccessibilityNode("field", role="AXTextField", title="Search")
    root = AccessibilityNode("root", role="AXApplication", children=[button, field])

    class Backend:
        def application_name(self): return "Test"
        def tree(self): return root
        def focused(self): return field
        def perform(self, node, operation): pass

    inspector = AccessibilityInspector(Backend())
    assert inspector.find("Search button").element == "button"
    assert inspector.find("Search field").element == "field"
    with pytest.raises(Exception, match="ambiguous"):
        inspector.find("Search")


def test_compound_commands_support_comma_chains_and_preserve_text():
    assert split_compound("open Chrome, go to LeetCode, and search for Two Sum") == [
        "open Chrome", "go to LeetCode", "search for Two Sum",
    ]
    assert split_compound("type bread, butter and honey") == ["type bread, butter and honey"]


def test_compound_runner_stops_after_first_failure(monkeypatch, capsys):
    class FakeEngine:
        def __init__(self): self.calls = []
        def decide(self, transcript, context):
            self.calls.append(transcript)
            return Action(action="OPEN_APP", target="Notion")

    class FakeExecutor:
        def __init__(self, macos): pass
        def execute(self, action, dry_run=False): raise ValueError("Notion is not installed")

    monkeypatch.setattr("app.main.JevDecisionEngine", FakeEngine)
    monkeypatch.setattr("app.main.ActionExecutor", FakeExecutor)
    monkeypatch.setattr("app.main.installed_applications", list)
    assert run_text("open Notion and type hello", dry_run=False) == 1
    assert "Compound command aborted." in capsys.readouterr().out
