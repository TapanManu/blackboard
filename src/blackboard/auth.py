"""Capability grants (Delta10).

Topic isolation is enforced HERE, from the token, on every call. Never from a
request parameter and never from the agent's prompt: a prompt-level instruction
not to read a topic is advisory, a scoped token is not.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from typing import Optional

from .errors import Forbidden
from .store.base import Grant
from .uri import any_glob_match

CAPS = ("read", "write", "link", "admin")
ROLE_CAPS = {
    "planner": ["read", "write", "link"],
    "worker": ["read", "write"],
    "reader": ["read"],
    "admin": ["read", "write", "link", "admin"],
}


def new_token() -> str:
    return "bbt_" + secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue(store, workspace: str, role: str, topic_globs, agent_id: Optional[str] = None,
          ttl_s: Optional[int] = None, caps=None) -> tuple:
    token = new_token()
    g = Grant(
        token_hash=token_hash(token),
        agent_id=agent_id or f"{role}-{secrets.token_hex(3)}",
        role=role, workspace=workspace,
        topic_globs=list(topic_globs) or ["**"],
        caps=list(caps or ROLE_CAPS.get(role, ["read"])),
        issued_at=int(time.time()),
        expires_at=int(time.time()) + ttl_s if ttl_s else None,
    )
    store.put_grant(g)
    return token, g


def resolve(store, token: str) -> Grant:
    g = store.get_grant(token_hash(token)) if token else None
    if g is None:
        raise Forbidden("unknown or revoked token")
    if g.expires_at and g.expires_at < time.time():
        raise Forbidden("token expired", expired_at=g.expires_at)
    return g


def check(grant: Grant, cap: str, workspace: str, path: Optional[str] = None) -> None:
    """`path` is `<topic>/<kind>/<id>`. Raises Forbidden; never returns False."""
    if cap not in grant.caps:
        raise Forbidden(f"capability {cap!r} not granted", role=grant.role, caps=grant.caps)
    if workspace != grant.workspace:
        raise Forbidden("workspace outside grant", granted=grant.workspace, requested=workspace)
    if path is None:
        return
    if not any_glob_match(grant.topic_globs, path):
        # Deliberately does not reveal whether the entry exists.
        raise Forbidden("topic outside grant", path=path, topic_globs=grant.topic_globs)
