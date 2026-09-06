"""bb:// addressing and topic-glob authorization.

    bb://<workspace>/<topic>/<kind>/<id>[@<version>]
    bb-artifact://sha256/<hex>

`topic` is a dotted hierarchy in a single path segment: `domain.automotive`, `tasks.car`.
Grants match against the path form `<topic>/<kind>/<id>` (see `glob_match`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .errors import InvalidURI

SEGMENT = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*$")
_URI = re.compile(
    r"^bb://(?P<ws>[^/]+)/(?P<topic>[^/]+)/(?P<kind>[^/]+)/(?P<id>[^/@]+)(?:@(?P<version>\d+))?$"
)
ARTIFACT = re.compile(r"^bb-artifact://sha256/(?P<hex>[0-9a-f]{64})$")

KINDS = {
    "task_spec", "result", "decision", "fact", "artifact_ref",
    "runbook", "summary", "state", "question", "critique",
}


@dataclass(frozen=True)
class URI:
    workspace: str
    topic: str
    kind: str
    id: str
    version: Optional[int] = None

    @property
    def path(self) -> str:
        """The authorization path: everything a grant glob is matched against."""
        return f"{self.topic}/{self.kind}/{self.id}"

    def base(self) -> str:
        """Version-less canonical form. This is the entry's primary key."""
        return f"bb://{self.workspace}/{self.topic}/{self.kind}/{self.id}"

    def __str__(self) -> str:
        return self.base() + (f"@{self.version}" if self.version is not None else "")


def parse(raw: str) -> URI:
    if not isinstance(raw, str):
        raise InvalidURI("uri must be a string", got=type(raw).__name__)
    m = _URI.match(raw.strip())
    if not m:
        raise InvalidURI(
            "expected bb://<workspace>/<topic>/<kind>/<id>[@<version>]", uri=raw
        )
    parts = m.groupdict()
    for field in ("ws", "topic", "kind", "id"):
        if not SEGMENT.match(parts[field]):
            raise InvalidURI(f"illegal characters in {field}", uri=raw, segment=parts[field])
    v = parts["version"]
    return URI(parts["ws"], parts["topic"], parts["kind"], parts["id"],
               int(v) if v is not None else None)


def artifact_uri(sha256_hex: str) -> str:
    return f"bb-artifact://sha256/{sha256_hex}"


def parse_artifact(raw: str) -> str:
    m = ARTIFACT.match(raw.strip())
    if not m:
        raise InvalidURI("expected bb-artifact://sha256/<64 hex>", uri=raw)
    return m.group("hex")


# --------------------------------------------------------------------------- globs

def _glob_to_regex(pattern: str) -> str:
    """`**` crosses `/`; `*` does not; `?` is one non-`/` char. Everything else is literal.

    Deliberately not fnmatch: fnmatch's `*` crosses separators, which would make
    `domain.automotive/*` match `domain.armaments/...` under some topic spellings.
    Topic isolation is load-bearing (Delta10), so the matcher is written out.
    """
    out, i, n = ["^"], 0, len(pattern)
    while i < n:
        c = pattern[i]
        if c == "/" and pattern[i + 1:i + 3] == "**":
            # `a/**` matches `a` itself as well as anything beneath it.
            out.append("(?:/.*)?")
            i += 3
            continue
        if c == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                out.append(".*")
                i += 2
                if i < n and pattern[i] == "/":   # `**/` also matches zero segments
                    out.append("/?")
                    i += 1
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    out.append("$")
    return "".join(out)


_GLOB_CACHE: dict[str, re.Pattern] = {}


def glob_match(pattern: str, path: str) -> bool:
    """Match a grant glob against a `<topic>/<kind>/<id>` path."""
    rx = _GLOB_CACHE.get(pattern)
    if rx is None:
        rx = _GLOB_CACHE[pattern] = re.compile(_glob_to_regex(pattern))
    return rx.match(path) is not None


def any_glob_match(patterns, path: str) -> bool:
    return any(glob_match(p, path) for p in patterns)


def topic_prefix(pattern: str) -> Optional[str]:
    """Literal prefix of a glob, for narrowing a SQL scan before the regex pass."""
    cut = len(pattern)
    for ch in "*?":
        j = pattern.find(ch)
        if j != -1:
            cut = min(cut, j)
    return pattern[:cut] or None
