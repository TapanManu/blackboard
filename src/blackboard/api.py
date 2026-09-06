"""The five L0 operations. One implementation, shared by the MCP server and the CLI.

    get_state · update_state · list_keys · search_keys · link_state

Every call is authorized from the caller's grant (Delta10), every read is
budget-capped and reports omissions (Delta8), every write carries a digest (Delta7).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional, Sequence

from . import uri as uri_mod
from .artifacts import THRESHOLD_BYTES, LocalArtifacts, sha256_bytes
from .auth import check, resolve
from .digest import MAX_DIGEST_TOKENS, auto_digest, truncate_to_tokens
from .errors import DigestRequired, InvalidURI, NotFound, PayloadError
from .render import MODES, canonical, pack, render_entry
from .store.base import Entry
from .tokens import est_tokens

REL_KINDS = {"depends_on", "derived_from", "supersedes", "refines",
             "cites", "part_of", "contradicts"}
DEFAULT_BUDGET = 2000
MAX_BUDGET = 8000


class Blackboard:
    def __init__(self, store, artifacts, workspace: str):
        self.store = store
        self.artifacts = artifacts
        self.workspace = workspace

    # ------------------------------------------------------------------ util
    def _resolve_body(self, e: Entry):
        if e.body is not None:
            return json.loads(e.body)
        if e.artifact_uri:
            raw = self.artifacts.get(e.artifact_uri)
            if raw is None:
                raise PayloadError("artifact missing from store", uri=e.uri,
                                   artifact_uri=e.artifact_uri)
            return json.loads(raw.decode())
        return None

    # -------------------------------------------------------------- get_state
    def get_state(self, grant, uris, mode: str = "digest", fields=None,
                  budget_tokens: int = DEFAULT_BUDGET) -> dict:
        if isinstance(uris, str):
            uris = [uris]
        if mode not in MODES:
            raise InvalidURI(f"unknown mode {mode!r}", allowed=list(MODES))
        budget = max(200, min(int(budget_tokens), MAX_BUDGET))

        parsed, missing = [], []
        for raw in uris:
            u = uri_mod.parse(raw)
            check(grant, "read", u.workspace, u.path)
            parsed.append(u)

        items = []
        for u in parsed:
            e = self.store.get(u.base(), u.version)
            if e is None:
                missing.append(str(u))
                continue
            body = self._resolve_body(e) if mode in ("fields", "table", "full") else None
            items.append(render_entry(e, mode, fields, body))

        self.store.touch_reads([i["uri"] for i in items])
        out = pack(items, budget)
        if missing:
            out["not_found"] = missing
        return out

    # ----------------------------------------------------------- update_state
    def update_state(self, grant, uri: str, body=None, digest: Optional[str] = None,
                     expect_version: Optional[int] = None, sources=None,
                     confidence: Optional[float] = None, schema_id: Optional[str] = None,
                     source_path: Optional[str] = None, auto_digest_ok: bool = False,
                     status: str = "accepted") -> dict:
        u = uri_mod.parse(uri)
        check(grant, "write", u.workspace, u.path)
        if (body is None) == (source_path is None):
            raise PayloadError("provide exactly one of body or source_path")

        generated = False
        artifact_uri_ = None

        if source_path is not None:
            # Delta12: the DAEMON reads the file. Bulk content never enters a context window.
            p = Path(source_path).expanduser().resolve()
            if not p.is_file():
                raise PayloadError("source_path is not a readable file", path=str(p))
            raw = p.read_bytes()
            artifact_uri_ = self.artifacts.put(raw)
            body_obj = {"artifact_uri": artifact_uri_, "source_name": p.name,
                        "bytes": len(raw), "sha256": sha256_bytes(raw)}
            text = canonical(body_obj)
            if not digest:
                digest = truncate_to_tokens(
                    f"[auto] {u.kind}: ingested file {p.name} ({len(raw)} bytes) -> {artifact_uri_}")
                generated = True
            n_bytes, body_store = len(raw), text
        else:
            body_obj = body
            text = canonical(body_obj)
            n_bytes = len(text.encode())
            if not digest:
                if not auto_digest_ok:
                    raise DigestRequired(
                        "every entry needs a digest (<=200 tokens); "
                        "pass one, or set auto_digest=true to accept a structural stub",
                        uri=uri)
                digest = auto_digest(u.kind, body_obj)
                generated = True
            if n_bytes > THRESHOLD_BYTES:
                artifact_uri_ = self.artifacts.put(text.encode())
                body_store = None
            else:
                body_store = text

        if est_tokens(digest) > MAX_DIGEST_TOKENS:
            digest = truncate_to_tokens(digest)

        e = Entry(
            uri=u.base(), workspace=u.workspace, topic=u.topic, kind=u.kind, id=u.id,
            version=0, digest=digest, body=body_store, artifact_uri=artifact_uri_,
            body_hash=sha256_bytes(text.encode()), bytes=n_bytes,
            est_tokens=est_tokens(text), status=status, producer=grant.agent_id,
            confidence=confidence, sources=list(sources or []),
            digest_generated=generated, schema_id=schema_id,
        )
        e = self.store.put(e, expect_version)
        self.store.append_event(u.workspace, u.topic, "put", e.uri, grant.agent_id,
                                {"version": e.version})

        warnings = []
        if generated:
            warnings.append("digest was auto-generated; nobody described this entry on purpose")
        if body is not None and not sources and u.kind in ("fact", "result", "decision"):
            warnings.append("no sources cited; unsourced claims are not verifiable")
        return {"uri": e.uri, "version": e.version, "digest": e.digest,
                "est_tokens": e.est_tokens, "artifact_uri": e.artifact_uri,
                "warnings": warnings}

    # -------------------------------------------------------------- list_keys
    def list_keys(self, grant, topic: Optional[str] = None, kind: Optional[str] = None,
                  status: Optional[str] = None, order: str = "recency", limit: int = 20,
                  mode: str = "digest", fields=None,
                  budget_tokens: int = DEFAULT_BUDGET) -> dict:
        check(grant, "read", self.workspace)
        if mode not in ("digest", "table", "ref", "fields"):
            raise InvalidURI("list_keys supports digest|table|ref|fields", got=mode)
        budget = max(200, min(int(budget_tokens), MAX_BUDGET))
        glob = topic or "**"
        rows = self.store.query(self.workspace, glob, kind, status, order,
                                max(1, min(int(limit), 200)))
        # A grant is a hard filter, not a warning: out-of-scope rows are never listed.
        rows = [e for e in rows
                if uri_mod.any_glob_match(grant.topic_globs, f"{e.topic}/{e.kind}/{e.id}")]

        if mode == "table":
            recs = [{"uri": e.uri, "kind": e.kind, "topic": e.topic, "version": e.version,
                     "est_tokens": e.est_tokens, "producer": e.producer,
                     "updated_at": e.updated_at, "digest": e.digest} for e in rows]
            from .render import to_tsv
            tsv = to_tsv(recs, fields)
            return {"format": "tsv", "rows": len(recs), "content": tsv,
                    "spent_tokens": est_tokens(tsv), "truncated": False, "omitted": 0}

        items = []
        for e in rows:
            body = self._resolve_body(e) if mode == "fields" else None
            items.append(render_entry(e, "digest" if mode == "digest" else mode, fields, body))
        self.store.touch_reads([i["uri"] for i in items])
        return pack(items, budget)

    # ------------------------------------------------------------ search_keys
    def search_keys(self, grant, q: str, topic: Optional[str] = None,
                    limit: int = 10) -> dict:
        check(grant, "read", self.workspace)
        hits = self.store.search(self.workspace, q, limit * 4)
        out = []
        for uri_str, score in hits:
            try:
                u = uri_mod.parse(uri_str)
            except InvalidURI:
                continue
            if not uri_mod.any_glob_match(grant.topic_globs, u.path):
                continue
            if topic and not uri_mod.glob_match(topic, u.path) \
                    and not uri_mod.glob_match(topic, u.topic):
                continue
            e = self.store.get(uri_str)
            if e:
                out.append({"uri": e.uri, "kind": e.kind, "topic": e.topic,
                            "digest": e.digest, "score": round(score, 4),
                            "est_tokens": e.est_tokens})
            if len(out) >= limit:
                break
        return {"items": out, "spent_tokens": est_tokens(canonical(out)),
                "truncated": False, "omitted": 0}

    # -------------------------------------------------------------- link_state
    def link_state(self, grant, src: str, rel: str, dst) -> dict:
        if isinstance(dst, str):
            dst = [dst]
        if rel not in REL_KINDS:
            raise InvalidURI(f"unknown rel {rel!r}", allowed=sorted(REL_KINDS))
        s = uri_mod.parse(src)
        check(grant, "link", s.workspace, s.path)
        dsts = []
        for d in dst:
            du = uri_mod.parse(d)
            check(grant, "read", du.workspace, du.path)
            dsts.append(du.base())
        n = self.store.link(s.base(), rel, dsts)
        self.store.append_event(s.workspace, s.topic, "link", s.base(), grant.agent_id,
                                {"rel": rel, "n": n})
        return {"src": s.base(), "rel": rel, "linked": n,
                "dst": dsts, "spent_tokens": 0}

    def events(self, grant, cursor: int = 0, limit: int = 100) -> dict:
        """Read the append-only event log. Not an agent tool in L0 -- the watch/
        long-poll primitive is L2. Exposed here so the log is not write-only:
        `status --events` and any external observer can follow it."""
        check(grant, "read", self.workspace)
        rows = self.store.events_since(self.workspace, cursor, limit)
        rows = [r for r in rows if r.get("uri") is None
                or uri_mod.any_glob_match(grant.topic_globs,
                                          uri_mod.parse(r["uri"]).path)]
        return {"events": rows, "cursor": rows[-1]["seq"] if rows else cursor}

    # ------------------------------------------------------------------ admin
    def health(self) -> dict:
        st = self.store.stats(self.workspace)
        rows = self.store.query(self.workspace, "**", None, None, "recency", 2000)
        dangling, auto = 0, 0
        known = {e.uri for e in rows}
        for e in rows:
            if e.digest_generated:
                auto += 1
            for _rel, dst in self.store.links_from(e.uri):
                if dst not in known:
                    dangling += 1
        n = max(1, len(rows))
        f_dangling = min(1.0, dangling / n)
        f_auto = auto / n
        score = round(0.60 * (1 - f_dangling) + 0.40 * (1 - f_auto), 3)
        return {**st, "dangling_refs": dangling, "auto_digests": auto,
                "board_health": score,
                "note": "L0 health = link coherence + digest authorship. "
                        "Trust and contest signals arrive with L3."}

    def export_jsonl(self, path: str) -> int:
        rows = self.store.query(self.workspace, "**", None, None, "created", 100000)
        with open(path, "w") as fh:
            for e in rows:
                rec = {"uri": e.uri, "version": e.version, "kind": e.kind, "topic": e.topic,
                       "digest": e.digest, "body": self._resolve_body(e),
                       "sources": e.sources, "producer": e.producer,
                       "created_at": e.created_at, "updated_at": e.updated_at,
                       "links": self.store.links_from(e.uri)}
                fh.write(json.dumps(rec) + "\n")
        return len(rows)
