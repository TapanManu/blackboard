"""Storage interface.

Shaped so a Postgres driver (L4) can be added without changing it. SQLite
semantics must not leak through: no `sqlite3` types, no `?` placeholders, no
`lastrowid` in any signature here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, Sequence


@dataclass
class Entry:
    uri: str
    workspace: str
    topic: str
    kind: str
    id: str
    version: int
    digest: str
    body: Optional[str] = None            # canonical JSON text, or None if externalized
    artifact_uri: Optional[str] = None
    body_hash: str = ""
    bytes: int = 0
    est_tokens: int = 0
    status: str = "accepted"
    producer: str = ""
    model: Optional[str] = None
    confidence: Optional[float] = None
    sources: list = field(default_factory=list)
    trust: float = 0.0                    # [L3] dormant in L0
    digest_generated: bool = False
    schema_id: Optional[str] = None
    reads: int = 0
    last_read_at: Optional[int] = None
    created_at: int = 0
    updated_at: int = 0


@dataclass
class Grant:
    token_hash: str
    agent_id: str
    role: str
    workspace: str
    topic_globs: list
    caps: list
    issued_at: int
    expires_at: Optional[int] = None


class Store(Protocol):
    # lifecycle
    def init_schema(self) -> None: ...
    def close(self) -> None: ...

    # entries
    def get(self, uri: str, version: Optional[int] = None) -> Optional[Entry]: ...
    def get_many(self, uris: Sequence[str]) -> list: ...
    def put(self, entry: Entry, expect_version: Optional[int]) -> Entry: ...
    def query(self, workspace: str, topic_glob: Optional[str], kind: Optional[str],
              status: Optional[str], order: str, limit: int) -> list: ...
    def search(self, workspace: str, q: str, limit: int) -> list: ...
    def history(self, uri: str) -> list: ...
    def touch_reads(self, uris: Sequence[str]) -> None: ...

    # links
    def link(self, src: str, rel: str, dsts: Sequence[str]) -> int: ...
    def links_from(self, src: str) -> list: ...
    def links_to(self, dst: str) -> list: ...

    # events
    def append_event(self, workspace: str, topic: str, type_: str,
                     uri: Optional[str], actor: str, payload: Optional[dict]) -> int: ...
    def events_since(self, workspace: str, cursor: int, limit: int) -> list: ...

    # grants
    def put_grant(self, grant: Grant) -> None: ...
    def get_grant(self, token_hash: str) -> Optional[Grant]: ...
    def list_grants(self, workspace: str) -> list: ...
    def delete_grant(self, token_hash: str) -> bool: ...

    # ops
    def stats(self, workspace: str) -> dict: ...
