"""CLI. Stdlib argparse: no runtime dependency, install is one command (R4)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import config
from .auth import ROLE_CAPS, issue, token_hash
from .conventions import state_uri
from .errors import BlackboardError


def _api(args):
    return config.open_workspace(args.workspace, memory=getattr(args, "ephemeral", False))


def cmd_init(args):
    api, store = _api(args)
    st = store.stats(args.workspace)
    print(f"workspace  {args.workspace}")
    print(f"database   {config.db_path(args.workspace)}")
    print(f"artifacts  {config.artifacts_path()}")
    print(f"entries    {st['entries']}")
    print(f"\nNext: blackboard-mcp --workspace {args.workspace} grant --role planner")
    return 0


def cmd_grant(args):
    _api_, store = _api(args)
    globs = [g.strip() for g in args.topics.split(",") if g.strip()] or ["**"]
    token, g = issue(store, args.workspace, args.role, globs,
                     agent_id=args.agent_id, ttl_s=args.ttl)
    if args.quiet:
        print(token)
        return 0
    print(f"agent_id    {g.agent_id}")
    print(f"role        {g.role}   caps={','.join(g.caps)}")
    print(f"topics      {','.join(g.topic_globs)}")
    print(f"expires     {g.expires_at or 'never'}")
    print(f"\ntoken (shown once, store it now):\n{token}")
    return 0


def cmd_revoke(args):
    _api_, store = _api(args)
    ok = store.delete_grant(args.token_hash if len(args.token_hash) == 64
                            else token_hash(args.token_hash))
    print("revoked" if ok else "no such grant")
    return 0 if ok else 1


def cmd_grants(args):
    _api_, store = _api(args)
    for g in store.list_grants(args.workspace):
        print(f"{g['agent_id']:<20} {g['role']:<9} {g['topic_globs']}")
    return 0


def cmd_status(args):
    api, _store = _api(args)
    st = api.health()
    print(f"entries        {st['entries']}")
    print(f"bytes          {st['bytes']}")
    print(f"est_tokens     {st['est_tokens']}")
    print(f"event cursor   {st['cursor']}")
    print(f"board_health   {st['board_health']}")
    print(f"dangling refs  {st['dangling_refs']}")
    print(f"auto digests   {st['auto_digests']}")
    if st["kinds"]:
        print("kinds          " + ", ".join(f"{k}={v}" for k, v in sorted(st["kinds"].items())))
    if st["topics"]:
        print("topics         " + ", ".join(f"{k}={v}" for k, v in sorted(st["topics"].items())))
    return 0


def cmd_events(args):
    api, store = _api(args)
    from .auth import issue as _issue
    _t, g = _issue(store, args.workspace, "admin", ["**"], agent_id="cli")
    out = api.events(g, args.since, args.limit)
    for e in out["events"]:
        print(f"{e['seq']:>6}  {e['type']:<6} {e['actor']:<14} {e['uri'] or ''}")
    print(f"cursor {out['cursor']}")
    return 0


def cmd_health(args):
    api, _store = _api(args)
    print(json.dumps(api.health(), indent=2))
    return 0


def cmd_export(args):
    api, _store = _api(args)
    n = api.export_jsonl(args.out)
    print(f"exported {n} entries -> {args.out}")
    return 0


def _rewrite_ws(uri: str, workspace: str, keep: bool) -> str:
    """Exported URIs carry their source workspace. A dump must be portable, so by
    default the workspace segment is rebased onto the target."""
    if keep:
        return uri
    from .uri import parse
    u = parse(uri)
    return f"bb://{workspace}/{u.topic}/{u.kind}/{u.id}"


def cmd_import(args):
    api, store = _api(args)
    from .auth import issue as _issue
    _t, g = _issue(store, args.workspace, "admin", ["**"], agent_id="importer")
    n, links = 0, []
    with open(args.src) as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            uri = _rewrite_ws(rec["uri"], args.workspace, args.keep_workspace)
            api.update_state(g, uri, body=rec.get("body"),
                             digest=rec.get("digest"), sources=rec.get("sources"),
                             auto_digest_ok=True)
            for rel, dst in rec.get("links") or []:
                links.append((uri, rel, _rewrite_ws(dst, args.workspace, args.keep_workspace)))
            n += 1
    # Links are applied after every entry exists, so import order cannot create dangles.
    for src, rel, dst in links:
        api.link_state(g, src, rel, [dst])
    print(f"imported {n} entries, {len(links)} links")
    return 0


def cmd_destroy(args):
    p = config.db_path(args.workspace)
    if not args.yes:
        print(f"This deletes {p} and its history. Re-run with --yes.")
        return 1
    for suffix in ("", "-wal", "-shm"):
        f = Path(str(p) + suffix)
        if f.exists():
            f.unlink()
    print(f"destroyed {args.workspace}")
    print("note: artifacts are content-addressed and shared; run `vacuum` to reclaim them")
    return 0


def cmd_vacuum(args):
    api, store = _api(args)
    rows = store.query(args.workspace, "**", None, None, "created", 1000000)
    live = {e.artifact_uri for e in rows if e.artifact_uri}
    root = config.artifacts_path()
    removed = kept = 0
    for f in root.rglob("*"):
        if not f.is_file() or f.suffix == ".tmp":
            continue
        uri = f"bb-artifact://sha256/{f.name}"
        if uri in live:
            kept += 1
        elif args.yes:
            f.unlink()
            removed += 1
        else:
            removed += 1
    store.conn.execute("VACUUM")
    print(f"artifacts: {kept} referenced, {removed} unreferenced "
          f"{'removed' if args.yes else '(dry run; pass --yes)'}")
    return 0


def cmd_serve(args):
    if args.stdio:
        from .server import serve_stdio
        return serve_stdio(args.workspace)
    print("only --stdio is implemented; the HTTP transport is part of the deferred "
          "cloud layer (see docs/05-running-on-kubernetes.md)",
          file=sys.stderr)
    return 2


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="blackboard-mcp",
                               description="Local context store for multi-agent LLM systems")
    p.add_argument("--workspace", "-w", default=os.environ.get("BLACKBOARD_WORKSPACE", "default"))
    p.add_argument("--ephemeral", action="store_true",
                   help="in-memory workspace; nothing is persisted")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(fn=cmd_init)

    g = sub.add_parser("grant")
    g.add_argument("--role", default="worker", choices=sorted(ROLE_CAPS))
    g.add_argument("--topics", default="**")
    g.add_argument("--agent-id", default=None)
    g.add_argument("--ttl", type=int, default=None, help="seconds")
    g.add_argument("--quiet", action="store_true", help="print only the token")
    g.set_defaults(fn=cmd_grant)

    r = sub.add_parser("revoke"); r.add_argument("token_hash"); r.set_defaults(fn=cmd_revoke)
    sub.add_parser("grants").set_defaults(fn=cmd_grants)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    ev = sub.add_parser("events")
    ev.add_argument("--since", type=int, default=0)
    ev.add_argument("--limit", type=int, default=100)
    ev.set_defaults(fn=cmd_events)
    sub.add_parser("health").set_defaults(fn=cmd_health)

    e = sub.add_parser("export"); e.add_argument("--out", required=True); e.set_defaults(fn=cmd_export)
    i = sub.add_parser("import")
    i.add_argument("src")
    i.add_argument("--keep-workspace", action="store_true",
                   help="preserve source workspace in URIs (exact restore)")
    i.set_defaults(fn=cmd_import)

    d = sub.add_parser("destroy"); d.add_argument("--yes", action="store_true"); d.set_defaults(fn=cmd_destroy)
    v = sub.add_parser("vacuum"); v.add_argument("--yes", action="store_true"); v.set_defaults(fn=cmd_vacuum)

    s = sub.add_parser("serve")
    s.add_argument("--stdio", action="store_true", default=True)
    s.set_defaults(fn=cmd_serve)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except BlackboardError as ex:
        print(json.dumps(ex.to_dict()), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
