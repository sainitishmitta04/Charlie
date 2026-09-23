from __future__ import annotations

import subprocess
from typing import Protocol


class MacOSExecutor(Protocol):
    def execute_open_app(self, app_name: str) -> str:
        """Open an application and return a user-facing result."""


class NativeMacOSExecutor:
    def execute_open_app(self, app_name: str) -> str:
        subprocess.run(["open", "-a", app_name], check=True)
        return f"Opening {app_name}."
