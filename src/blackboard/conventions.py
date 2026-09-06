"""L1 protocol constants.

These are CONVENTIONS, not enforcement. They live in code only so the CLI, the
resume test and the skill prompt cannot drift apart. Nothing here validates
anything; an agent that ignores it gets a working board and a worse experience.
"""
from __future__ import annotations

KINDS = ("task_spec", "result", "decision", "fact", "artifact_ref",
         "runbook", "summary", "state", "question", "critique")

RELS = ("depends_on", "derived_from", "supersedes", "refines",
        "cites", "part_of", "contradicts")

# Well-known URIs. Orientation is a convention on a fixed address, not a tool.
STATE_TOPIC = "run"


def state_uri(workspace: str) -> str:
    return f"bb://{workspace}/{STATE_TOPIC}/state/current"


def summary_uri(workspace: str) -> str:
    return f"bb://{workspace}/{STATE_TOPIC}/summary/final"


def task_spec_uri(workspace: str, lane: str, task_id: str) -> str:
    return f"bb://{workspace}/tasks.{lane}/task_spec/{task_id}"


def result_uri(workspace: str, lane: str, task_id: str) -> str:
    return f"bb://{workspace}/tasks.{lane}/result/{task_id}"


# The documented resume recipe (Q10). Reproduced here so the test drives exactly
# what the skill prompt tells an agent to do -- no privileged shortcut.
RESUME_RECIPE = [
    ("get_state",  {"uris": ["{state_uri}"], "mode": "full", "budget_tokens": 800}),
    ("list_keys",  {"topic": "tasks.**", "mode": "table", "limit": 40}),
    ("list_keys",  {"kind": "decision", "order": "recency", "limit": 10,
                    "mode": "digest", "budget_tokens": 900}),
]

RESUME_TOKEN_TARGET = 3000
