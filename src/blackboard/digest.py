"""Digest generation (Delta7).

Every entry carries a <=200-token summary. The writer should author it; when they
don't, this produces a deterministic structural one and the entry is flagged
`digest_generated=true` so a reader knows nobody described this on purpose.
"""
from __future__ import annotations

import json
from .tokens import est_tokens

MAX_DIGEST_TOKENS = 200


def truncate_to_tokens(text: str, budget: int = MAX_DIGEST_TOKENS) -> str:
    if est_tokens(text) <= budget:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if est_tokens(text[:mid]) <= budget - 1:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "…"


def _shape(v, depth=0):
    if depth > 2:
        return "..."
    if isinstance(v, dict):
        return "{" + ",".join(f"{k}:{_shape(x, depth+1)}" for k, x in list(v.items())[:8]) + "}"
    if isinstance(v, list):
        return f"[{len(v)}x {_shape(v[0], depth+1) if v else 'empty'}]"
    if isinstance(v, str):
        return f"str({len(v)})"
    if isinstance(v, bool):
        return "bool"
    if v is None:
        return "null"
    return type(v).__name__


def auto_digest(kind: str, body) -> str:
    """Deterministic structural digest. Never fabricates meaning it cannot see."""
    head = f"[auto] {kind}: "
    if isinstance(body, dict):
        keys = ", ".join(list(body.keys())[:12])
        preview = ""
        for k in ("objective", "summary", "title", "goal", "error", "name", "description"):
            if isinstance(body.get(k), str):
                preview = f" | {k}: {body[k][:180]}"
                break
        return truncate_to_tokens(f"{head}fields({keys}) {_shape(body)}{preview}")
    if isinstance(body, list):
        return truncate_to_tokens(f"{head}{len(body)} items, shape {_shape(body)}")
    text = body if isinstance(body, str) else json.dumps(body)
    return truncate_to_tokens(f"{head}{text[:400]}")
