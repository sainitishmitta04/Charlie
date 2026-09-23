from __future__ import annotations

import argparse

from app.actions.accessibility import AccessibilityError, AccessibilityInspector
from app.actions.executor import ActionExecutor
from app.actions.macos import NativeMacOSExecutor, installed_applications
from app.actions.schema import DecisionContext
from app.brain.jev import JevDecisionEngine
from app.commands.compound import split_compound


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Charlie macOS voice-control assistant")
    parser.add_argument("--text", help="Use text instead of microphone input")
    parser.add_argument("--dry-run", action="store_true", help="Decide but do not control macOS")
    parser.add_argument("--inspect-ui", action="store_true", help="Print the frontmost app's accessibility tree")
    return parser


def run_text(transcript: str, dry_run: bool = False) -> int:
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


def main() -> int:
    args = build_parser().parse_args()
    if args.inspect_ui:
        print(AccessibilityInspector().render())
        return 0
    if not args.text:
        raise SystemExit("MVP currently requires --text; microphone capture is the next phase")
    return run_text(args.text, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
