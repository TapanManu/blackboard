"""Claude Code hook handlers.

- pre-compact: saves where the work stood (git branch, HEAD, uncommitted files)
  to `bb://<ws>/run/state/compact-<session>` before the transcript is summarised.
- post-compact: appends Claude Code's own summary to that entry and makes it the digest.
"""
from __future__ import annotations

import subprocess
import sys
import time

from .digest import truncate_to_tokens
from .errors import NotFound

GIT_TIMEOUT_S = 3
MAX_STATUS_LINES = 50


def compact_uri(workspace: str, session_id: str) -> str:
    return f"bb://{workspace}/run/state/compact-{session_id or 'unknown'}"


def _git(cwd: str, *args: str):
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                           timeout=GIT_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def git_state(cwd: str) -> dict:
    status = _git(cwd, "status", "--short")
    if status is None:
        return {}
    lines = status.splitlines()
    return {"branch": _git(cwd, "branch", "--show-current"),
            "head": _git(cwd, "log", "-1", "--oneline"),
            "uncommitted": lines[:MAX_STATUS_LINES],
            "uncommitted_count": len(lines),
            "recent_commits": (_git(cwd, "log", "--oneline", "-5") or "").splitlines()}


def pre_compact(api, grant, workspace: str, payload: dict) -> dict:
    cwd = payload.get("cwd") or "."
    trigger = payload.get("trigger") or "manual"
    git = git_state(cwd)
    where = (f"branch {git['branch']} at {git['head']}, "
             f"{git['uncommitted_count']} uncommitted files" if git else "not a git repository")
    digest = (f"Checkpoint before {trigger} compaction in {cwd}: {where}. "
              "Claude Code's summary is appended once compaction finishes.")
    body = {"trigger": trigger, "session_id": payload.get("session_id"), "cwd": cwd,
            "at": int(time.time()), "git": git, "compact_summaries": []}
    return api.update_state(grant, compact_uri(workspace, payload.get("session_id")),
                            body=body, digest=digest)


def post_compact(api, grant, workspace: str, payload: dict) -> dict:
    summary = payload.get("compact_summary")
    if not isinstance(summary, str) or not summary.strip():
        return {}
    uri = compact_uri(workspace, payload.get("session_id"))
    digest = truncate_to_tokens(summary.strip())
    try:
        return api.update_state(grant, uri, append=summary, append_path="compact_summaries",
                                digest=digest)
    except NotFound:
        return api.update_state(grant, uri, body={"compact_summaries": [summary]}, digest=digest)


HANDLERS = {"pre-compact": pre_compact, "post-compact": post_compact}


def run_hook(api, grant, workspace: str, event: str, payload: dict) -> None:
    # A failing hook must never stand between the user and their compaction,
    # so every error is reported on stderr and swallowed.
    try:
        HANDLERS[event](api, grant, workspace, payload)
    except Exception as ex:  # noqa: BLE001
        print(f"blackboard {event} hook: {type(ex).__name__}: {ex}", file=sys.stderr)
