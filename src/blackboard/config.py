"""Paths and local security posture (R8: local storage, no egress)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT_ENV = "BLACKBOARD_HOME"


def home() -> Path:
    p = Path(os.environ.get(ROOT_ENV, Path.home() / ".blackboard"))
    p.mkdir(parents=True, exist_ok=True)
    os.chmod(p, 0o700)
    return p


def db_path(workspace: str) -> Path:
    return home() / f"{workspace}.db"


def artifacts_path() -> Path:
    return home() / "artifacts"


def open_workspace(workspace: str, memory: bool = False):
    """The one place a Blackboard is constructed. Returns (api, store)."""
    from .api import Blackboard
    from .artifacts import LocalArtifacts
    from .store.sqlite import SQLiteStore

    store = SQLiteStore(":memory:" if memory else str(db_path(workspace)))
    if not memory:
        p = db_path(workspace)
        if p.exists():
            os.chmod(p, 0o600)
    arts = LocalArtifacts(str(artifacts_path()))
    return Blackboard(store, arts, workspace), store
