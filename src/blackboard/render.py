"""The projection compiler (Delta5).

Tokens are counted on RENDERED text, not stored bytes. Storage is canonical JSON;
what a read costs is decided here.

  ref    -> uri + hash + est_tokens
  digest -> the <=200-token summary            (DEFAULT)
  fields -> only requested JSON paths
  table  -> TSV, header row + rows             (>=3 homogeneous records)
  full   -> canonical JSON
"""
from __future__ import annotations

import json
from typing import Optional, Sequence

from .tokens import est_tokens

MODES = ("ref", "digest", "fields", "table", "full")


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _get_path(obj, path: str):
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None
    return cur


def _flat(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, separators=(",", ":"), ensure_ascii=False)
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v).replace("\t", " ").replace("\n", " ")


def to_tsv(records: Sequence[dict], fields: Optional[Sequence[str]] = None) -> str:
    """Union of keys in order of first appearance, so heterogeneity degrades rather than fails."""
    if not records:
        return ""
    if fields:
        cols = list(fields)
    else:
        cols, seen = [], set()
        for r in records:
            for k in r:
                if k not in seen:
                    seen.add(k)
                    cols.append(k)
    lines = ["\t".join(cols)]
    for r in records:
        lines.append("\t".join(_flat(r.get(c)) for c in cols))
    return "\n".join(lines)


def wrap_untrusted(uri: str, producer: str, content: str) -> str:
    """Delta13: board content is data, never instructions."""
    return f'<bb:body uri="{uri}" producer="{producer}">\n{content}\n</bb:body>'


def render_entry(entry, mode: str = "digest", fields=None, body_obj=None) -> dict:
    """One entry -> the dict that goes on the wire. `body_obj` is the resolved body."""
    base = {"uri": entry.uri, "version": entry.version, "kind": entry.kind,
            "topic": entry.topic, "est_tokens": entry.est_tokens}
    if mode == "ref":
        return {**base, "hash": entry.body_hash,
                "artifact_uri": entry.artifact_uri}
    if mode == "digest":
        return {**base, "digest": entry.digest,
                "digest_generated": entry.digest_generated,
                "artifact_uri": entry.artifact_uri}
    if mode == "fields":
        sel = {f: _get_path(body_obj, f) for f in (fields or [])}
        return {**base, "digest": entry.digest,
                "content": wrap_untrusted(entry.uri, entry.producer, canonical(sel))}
    if mode == "table":
        recs = body_obj if isinstance(body_obj, list) else [body_obj]
        recs = [r if isinstance(r, dict) else {"value": r} for r in recs]
        return {**base, "digest": entry.digest, "format": "tsv",
                "content": wrap_untrusted(entry.uri, entry.producer, to_tsv(recs, fields))}
    if mode == "full":
        if body_obj is None and entry.artifact_uri:
            return {**base, "digest": entry.digest, "artifact_uri": entry.artifact_uri,
                    "note": "body is externalized; fetch the artifact by uri"}
        return {**base, "digest": entry.digest, "sources": entry.sources,
                "content": wrap_untrusted(entry.uri, entry.producer, canonical(body_obj))}
    raise ValueError(f"unknown mode {mode!r}; expected one of {MODES}")


def pack(items, budget_tokens: int, spent: int = 0) -> dict:
    """Fill up to a token budget, then stop and SAY WHAT WAS DROPPED (Delta8).

    Server-side enforcement is the difference between a board that saves tokens
    and a new way to blow up a context window.
    """
    out, omitted = [], []
    for it in items:
        cost = est_tokens(canonical(it))
        if out and spent + cost > budget_tokens:
            omitted.append(it.get("uri"))
            continue
        if not out and spent + cost > budget_tokens:
            out.append(it)          # always return at least one, else a read can never succeed
            spent += cost
            continue
        out.append(it)
        spent += cost
    return {"items": out, "spent_tokens": spent, "truncated": bool(omitted),
            "omitted": len(omitted), "omitted_uris": omitted[:50]}
