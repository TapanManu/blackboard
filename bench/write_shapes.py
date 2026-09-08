#!/usr/bin/env python3
"""What each write shape costs the author, in tokens they actually spend.

A write is paid twice over: once composing the tool-call arguments (output
tokens), once receiving the result (input tokens). Storage bytes are not part of
it -- they never enter a context window. So every figure here is
est_tokens(arguments) + est_tokens(result), counted with cl100k_base over the
same canonical JSON the server itself uses.

Each pair holds content constant and varies only the shape, which is the only
way the difference means anything. Run:

    .venv/bin/python bench/write_shapes.py            # table to stdout
    .venv/bin/python bench/write_shapes.py --write    # also refresh RESULTS.md
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from blackboard.render import canonical, wrap_untrusted            # noqa: E402
from blackboard.tokens import est_tokens, require_exact            # noqa: E402

URI = "bb://sedai/bench.write/result/exp2"
PRODUCER = "bench"

# Twelve real findings from the session that produced this write path.
COLUMNS = ["file", "line", "issue", "sev"]
ROWS = [
    ["src/blackboard/api.py", 145, "update_state echoed back the digest the author just composed", "high"],
    ["src/blackboard/api.py", 86, "extending an entry required reading it back and re-emitting the whole body", "high"],
    ["src/blackboard/server.py", 128, "grant resolved once at startup, so revoke and TTL were inert", "high"],
    ["src/blackboard/cli.py", 153, "vacuum built its live set from one workspace but artifacts are shared", "high"],
    ["src/blackboard/store/sqlite.py", 231, "vacuum ignored entry_history, deleting blobs old versions still read", "high"],
    [".mcp.json.example", 5, "uvx --from . omits the mcp extra, so the configured server exits 2", "med"],
    ["tests/test_render.py", 19, "savings test compared a heuristic count against an exact threshold", "med"],
    ["tests/test_tokens.py", 7, "importorskip hid the estimator error bound when tiktoken was absent", "med"],
    ["tests/test_mcp_e2e.py", 11, "importorskip hid the entire transport suite when mcp was absent", "med"],
    ["src/blackboard/api.py", 30, "no write shape existed for a set of homogeneous records", "med"],
    ["src/blackboard/api.py", 133, "the digest duplicated a summary the body already carried", "med"],
    ["src/blackboard/render.py", 89, "digest-only entries rendered as the string null", "low"],
]
OBJECTS = [dict(zip(COLUMNS, r)) for r in ROWS]
DIGEST = ("12 defects in the write path and its tests: 5 high (digest echo, whole-body "
          "re-emit on update, grant resolved at startup, vacuum scoped to one workspace, "
          "vacuum ignoring history), 6 med, 1 low")


def cost(args: dict, result: dict) -> int:
    """One write, as the author pays for it: arguments out, result back."""
    return est_tokens(canonical(args)) + est_tokens(canonical(result))


def old_result(digest: str, **extra) -> dict:
    """The pre-change reply: the digest echoed back, warnings as prose."""
    return {"uri": URI, "version": 1, "digest": digest, "est_tokens": 900,
            "artifact_uri": None, "warnings": [], **extra}


def new_result(**extra) -> dict:
    return {"uri": URI, "version": 1, "est_tokens": 900, "warnings": [], **extra}


def measure() -> list:
    out = []

    # 1. A findings list: objects with a key per value, vs columns named once.
    out.append(("A set of 12 findings",
                cost({"uri": URI, "body": OBJECTS, "digest": DIGEST}, old_result(DIGEST)),
                cost({"uri": URI, "columns": COLUMNS, "rows": ROWS, "digest": DIGEST},
                     new_result()),
                "body objects + echo", "columns+rows"))

    # 2. Same body either way; the digest is composed twice or lifted once.
    body = {"summary": DIGEST, "findings": OBJECTS}
    out.append(("A body that already summarises itself",
                cost({"uri": URI, "body": body, "digest": DIGEST}, old_result(DIGEST)),
                cost({"uri": URI, "body": body, "digest_from": "summary"}, new_result()),
                "digest typed again", "digest_from"))

    # 3. A small fact. The old path forced a body, so it restated the digest.
    small = "the grant is resolved once at process start, so revoke and TTL are inert"
    out.append(("One small fact",
                cost({"uri": URI, "body": {"finding": small}, "digest": small},
                     old_result(small)),
                cost({"uri": URI, "digest": small}, new_result()),
                "body restating digest", "digest alone"))

    # 4. Adding a 13th finding. Old: read the entry at full, re-emit all of it.
    #    The read is the server's own full-mode render, not an estimate of one.
    thirteenth = dict(zip(COLUMNS, ["src/blackboard/cli.py", 234,
                                    "vacuum had no way to reclaim superseded blobs", "med"]))
    read_back = est_tokens(canonical(
        {"uri": URI, "version": 1, "kind": "result", "topic": "bench.write",
         "est_tokens": 900, "digest": DIGEST, "sources": [],
         "content": wrap_untrusted(URI, PRODUCER, canonical(body))}))
    reemit = cost({"uri": URI, "body": {"summary": DIGEST, "findings": OBJECTS + [thirteenth]},
                   "digest": DIGEST, "expect_version": 1}, old_result(DIGEST, version=2))
    out.append(("Adding one finding to a running entry",
                read_back + reemit,
                cost({"uri": URI, "append": thirteenth, "append_path": "findings"},
                     new_result(version=2)),
                "get_state(full) + re-emit", "append"))

    # 5. The echo alone, held apart from every other change.
    out.append(("The result echo, on its own",
                est_tokens(canonical(old_result(DIGEST))),
                est_tokens(canonical(new_result())),
                "digest echoed back", "not echoed"))
    return out


def render(rows) -> str:
    head = (f"Tokenizer: cl100k_base (exact). Payload: 12 real findings, held constant "
            f"within each row.\n\n"
            f"| Write | Before | After | Saved |\n|---|---:|---:|---:|\n")
    body = "\n".join(
        f"| {name} — *{was} → {now}* | {a} | {b} | **{(a - b) / a:.0%}** |"
        for name, a, b, was, now in rows)
    tot_a, tot_b = sum(r[1] for r in rows[:-1]), sum(r[2] for r in rows[:-1])
    return (head + body +
            f"\n\nFour writes end to end (the echo row is a component of the others, "
            f"not a fifth write): **{tot_a} → {tot_b} tokens, {(tot_a - tot_b) / tot_a:.0%} "
            f"less**.\n\n"
            "Reading these: each row is a *whole write* — uri, digest, arguments and the "
            "result that comes back. The 34% the skill quotes for `columns`+`rows` is the "
            "row payload alone, which is why the same change reads lower here: the digest "
            "and the reply are identical on both sides and dilute the ratio. Neither "
            "number is wrong; they measure different brackets.\n")


if __name__ == "__main__":
    require_exact("a published token saving")
    text = render(measure())
    print(text)
    if "--write" in sys.argv:
        out = pathlib.Path(__file__).resolve().parent / "RESULTS.md"
        out.write_text("# Write-path cost, by shape\n\n"
                       "Generated by `bench/write_shapes.py`. Re-run it; do not hand-edit.\n\n"
                       + text)
        print(f"wrote {out}")
