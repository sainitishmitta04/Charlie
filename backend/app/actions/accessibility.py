from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class AccessibilityNode:
    element: Any
    role: str = ""
    title: str = ""
    description: str = ""
    role_description: str = ""
    identifier: str = ""
    children: list[AccessibilityNode] = field(default_factory=list)

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(value for value in (self.title, self.description, self.identifier, self.role_description) if value)

    @property
    def display_name(self) -> str:
        return next(iter(self.labels), self.role)


class AccessibilityBackend(Protocol):
    def application_name(self) -> str:
        ...

    def tree(self) -> AccessibilityNode:
        ...

    def focused(self) -> AccessibilityNode | None:
        ...

    def perform(self, node: AccessibilityNode, operation: str) -> None:
        ...


class AccessibilityError(RuntimeError):
    pass


class AccessibilityInspector:
    def __init__(self, backend: AccessibilityBackend | None = None) -> None:
        self.backend = backend or NativeAccessibilityBackend()

    def tree(self) -> AccessibilityNode:
        return self.backend.tree()

    def target_names(self) -> list[str]:
        names: list[str] = []
        for node in self._walk(self.tree()):
            names.extend(node.labels)
        return list(dict.fromkeys(name for name in names if name))

    def find(self, target: str) -> AccessibilityNode:
        wanted = target.casefold().strip()
        nodes = list(self._walk(self.tree()))
        exact = [node for node in nodes if any(label.casefold() == wanted for label in node.labels)]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            raise AccessibilityError(f"Accessibility target is ambiguous: {target}")
        partial = [node for node in nodes if any(wanted in label.casefold() for label in node.labels)]
        if len(partial) == 1:
            return partial[0]
        if not partial:
            raise AccessibilityError(f"Accessibility target not found: {target}")
        raise AccessibilityError(f"Accessibility target is ambiguous: {target}")

    def click(self, target: str) -> str:
        self.backend.perform(self.find(target), "AXPress")
        return f"Pressed {target}."

    def select(self, target: str) -> str:
        self.backend.perform(self.find(target), "AXSelect")
        return f"Selected {target}."

    def focus(self, target: str) -> str:
        self.backend.perform(self.find(target), "AXFocus")
        return f"Focused {target}."

    def read_focused(self) -> str:
        node = self.backend.focused()
        if node is None:
            return "No focused accessibility element found."
        return self._describe(node)

    def render(self) -> str:
        root = self.tree()
        lines = [f"Application: {self.backend.application_name()}", ""]
        self._render_node(root, lines, prefix="", is_last=True)
        return "\n".join(lines)

    @classmethod
    def _walk(cls, node: AccessibilityNode):
        yield node
        for child in node.children:
            yield from cls._walk(child)

    @staticmethod
    def _describe(node: AccessibilityNode) -> str:
        details = [node.role or "AXElement"]
        if node.title:
            details.append(f"title={node.title!r}")
        if node.description:
            details.append(f"description={node.description!r}")
        if node.role_description:
            details.append(f"role_description={node.role_description!r}")
        if node.identifier:
            details.append(f"identifier={node.identifier!r}")
        return " ".join(details)

    @classmethod
    def _render_node(cls, node: AccessibilityNode, lines: list[str], prefix: str, is_last: bool) -> None:
        branch = "└── " if is_last else "├── "
        lines.append(f"{prefix}{branch}{cls._describe(node)}")
        child_prefix = prefix + ("    " if is_last else "│   ")
        for index, child in enumerate(node.children):
            cls._render_node(child, lines, child_prefix, index == len(node.children) - 1)


class NativeAccessibilityBackend:
    _ATTRIBUTES = (
        "AXRole", "AXTitle", "AXDescription", "AXRoleDescription", "AXIdentifier", "AXChildren",
    )

    def __init__(self) -> None:
        try:
            import ApplicationServices as application_services  # type: ignore
        except ImportError as error:
            raise AccessibilityError("PyObjC ApplicationServices is required for Accessibility integration") from error
        self._as = application_services
        try:
            from AppKit import NSWorkspace  # type: ignore
        except ImportError as error:
            raise AccessibilityError("PyObjC AppKit is required for Accessibility integration") from error
        self._workspace = NSWorkspace

    def _frontmost_application(self) -> Any:
        app = self._workspace.sharedWorkspace().frontmostApplication()
        if app is None:
            raise AccessibilityError("No frontmost application found")
        return app

    def _app_element(self) -> Any:
        app = self._frontmost_application()
        return self._as.AXUIElementCreateApplication(app.processIdentifier())

    def application_name(self) -> str:
        return str(self._frontmost_application().localizedName() or "Unknown")

    def tree(self) -> AccessibilityNode:
        return self._node(self._app_element(), set(), 0)

    def focused(self) -> AccessibilityNode | None:
        system = self._as.AXUIElementCreateSystemWide()
        application = self._value(system, "AXFocusedApplication")
        if application is None:
            return None
        element = self._value(application, "AXFocusedUIElement")
        return self._node(element, set(), 0) if element is not None else None

    def perform(self, node: AccessibilityNode, operation: str) -> None:
        if operation == "AXFocus":
            error = self._as.AXUIElementSetAttributeValue(node.element, "AXFocused", True)
        elif operation == "AXSelect":
            error = self._as.AXUIElementPerformAction(node.element, "AXPress")
        else:
            error = self._as.AXUIElementPerformAction(node.element, operation)
        if error != 0:
            raise AccessibilityError(f"Accessibility operation {operation} failed with error {error}")

    def _node(self, element: Any, seen: set[int], depth: int) -> AccessibilityNode:
        if depth > 40:
            return AccessibilityNode(element, role="AXDepthLimit")
        identity = id(element)
        if identity in seen:
            return AccessibilityNode(element, role="AXCycle")
        seen.add(identity)
        values = {attribute: self._value(element, attribute) for attribute in self._ATTRIBUTES[:-1]}
        children = [self._node(child, seen, depth + 1) for child in (self._value(element, "AXChildren") or [])]
        return AccessibilityNode(
            element=element,
            role=str(values["AXRole"] or ""),
            title=str(values["AXTitle"] or ""),
            description=str(values["AXDescription"] or ""),
            role_description=str(values["AXRoleDescription"] or ""),
            identifier=str(values["AXIdentifier"] or ""),
            children=children,
        )

    def _value(self, element: Any, attribute: str) -> Any:
        try:
            error, value = self._as.AXUIElementCopyAttributeValue(element, attribute, None)
        except (AttributeError, TypeError, ValueError, RuntimeError):
            return None
        return value if error == 0 else None
