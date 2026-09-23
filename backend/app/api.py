from __future__ import annotations

from fastapi import FastAPI

from app.actions.schema import Action

app = FastAPI(title="Charlie", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "charlie"}


@app.post("/actions/validate", response_model=Action)
def validate_action(action: Action) -> Action:
    return action
