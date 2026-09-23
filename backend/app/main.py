from __future__ import annotations

import argparse

from app.actions.executor import ActionExecutor
from app.actions.macos import NativeMacOSExecutor
from app.actions.schema import DecisionContext
from app.brain.jev import JevDecisionEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Charlie macOS voice-control assistant")
    parser.add_argument("--text", help="Use text instead of microphone input")
    parser.add_argument("--dry-run", action="store_true", help="Decide but do not control macOS")
    return parser


def run_text(transcript: str, dry_run: bool = False) -> int:
    action = JevDecisionEngine().decide(transcript, DecisionContext(transcript=transcript))
    result = ActionExecutor(NativeMacOSExecutor()).execute(action, dry_run=dry_run)
    print(f"Transcript:\n{transcript}\n\nAction:\n{action.action.value}\n\nTarget:\n{action.target or '-'}\n\nExecution:\n{result}")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    if not args.text:
        raise SystemExit("MVP currently requires --text; microphone capture is the next phase")
    return run_text(args.text, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
