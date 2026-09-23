from dataclasses import dataclass, field

import pytest
from app.actions.accessibility import (
    AccessibilityError,
    AccessibilityInspector,
    AccessibilityNode,
)
from app.actions.executor import ActionExecutor
from app.actions.macos import NativeMacOSExecutor
from app.actions.schema import Action, ActionType
from app.brain.jev import JevDecisionEngine


@dataclass
class FakeBackend:
    root_node: AccessibilityNode
    focused_node: AccessibilityNode | None = None
    operations: list[tuple[str, object]] = field(default_factory=list)

    def application_name(self) -> str:
        return "Fake App"

    def tree(self) -> AccessibilityNode:
        return self.root_node

    def focused(self) -> AccessibilityNode | None:
        return self.focused_node

    def perform(self, node: AccessibilityNode, operation: str) -> None:
        self.operations.append((operation, node.element))


def make_backend() -> FakeBackend:
    continue_button = AccessibilityNode("continue", role="AXButton", title="Continue")
    search = AccessibilityNode(
        "search",
        role="AXTextField",
        description="Search field",
        identifier="global-search",
    )
    menu_item = AccessibilityNode("settings", role="AXMenuItem", title="Settings")
    root = AccessibilityNode("app", role="AXApplication", title="Fake App", children=[continue_button, search, menu_item])
    return FakeBackend(root, focused_node=search)


def test_inspector_matches_title_description_and_identifier():
    backend = make_backend()
    inspector = AccessibilityInspector(backend)
    assert inspector.find("Continue").element == "continue"
    assert inspector.find("Search field").element == "search"
    assert inspector.find("global-search").element == "search"


def test_accessibility_operations_are_deterministic_and_coordinate_free():
    backend = make_backend()
    inspector = AccessibilityInspector(backend)
    assert inspector.click("Continue") == "Pressed Continue."
    assert inspector.select("Settings") == "Selected Settings."
    assert inspector.focus("Search field") == "Focused Search field."
    assert backend.operations == [
        ("AXPress", "continue"),
        ("AXSelect", "settings"),
        ("AXFocus", "search"),
    ]


def test_focused_element_and_tree_render_are_readable():
    backend = make_backend()
    inspector = AccessibilityInspector(backend)
    assert "AXTextField" in inspector.read_focused()
    rendered = inspector.render()
    assert "Application: Fake App" in rendered
    assert "AXButton" in rendered and "Continue" in rendered
    assert "global-search" in rendered


def test_missing_and_ambiguous_targets_fail_closed():
    backend = make_backend()
    backend.root_node.children.append(AccessibilityNode("other", role="AXButton", title="Continue"))
    inspector = AccessibilityInspector(backend)
    with pytest.raises(AccessibilityError, match="ambiguous"):
        inspector.click("Continue")
    with pytest.raises(AccessibilityError, match="not found"):
        inspector.click("Not There")


def test_executor_dispatches_accessibility_actions_through_backend():
    backend = make_backend()
    executor = ActionExecutor(NativeMacOSExecutor(backend))
    result = executor.execute(Action(action=ActionType.ACCESSIBILITY_CLICK, target="Continue"))
    assert result == "Pressed Continue."
    assert backend.operations == [("AXPress", "continue")]


def test_accessibility_actions_require_targets_when_needed():
    with pytest.raises(ValueError, match="target"):
        Action(action=ActionType.ACCESSIBILITY_CLICK)
    assert Action(action=ActionType.ACCESSIBILITY_INSPECT)
    assert Action(action=ActionType.ACCESSIBILITY_READ_FOCUSED)


def test_jev_accessibility_target_must_come_from_accessibility_context():
    response = {
        "answers": {
            "action": {"choice": "ACCESSIBILITY_CLICK"},
            "accessibility_target": {"choice": "Continue"},
        }
    }
    action = JevDecisionEngine._parse_response(response, "click Continue", [], accessible_targets=["Continue"])
    assert action == Action(action=ActionType.ACCESSIBILITY_CLICK, target="Continue")
    with pytest.raises(ValueError, match="not offered"):
        JevDecisionEngine._parse_response(response, "click Continue", [], accessible_targets=["Cancel"])
