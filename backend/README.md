# Charlie backend

Phase 4 keeps text input and separates the system into four boundaries:

- `brain/`: decision engines. Jev is active; Laya has a reserved adapter.
- `actions/schema.py`: validated actions from an untrusted model response.
- `actions/registry.py` and `actions/macos.py`: the only macOS execution path.
- `actions/accessibility.py`: native AX-tree inspection and safe element actions.

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

Run tests and lint:

```bash
PYTHONPATH=backend python -m pytest backend/tests -q
uvx ruff check backend
```