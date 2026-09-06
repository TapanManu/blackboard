# MCP Tool Surface

Tool schemas are re-sent on **every turn of every agent**. The surface is a per-turn tax, so it is budgeted, not designed for completeness.

## L0 — five tools, ≤600 tokens of schema (the project)

> **Measured: 395 tokens** (`tests/test_server_budget.py`, exact cl100k_base). First implementation came in at 1,036 and the CI budget test rejected it; the fix was moving prose out of the JSON Schema into the L1 skill prompt, which loads once per session rather than every turn.

| Tool | Signature (abbrev.) | Notes |
|---|---|---|
| `update_state` | `(uri, body \| source_path, digest, expect_version?, sources[]?, confidence?)` → `{version, digest, warnings}` | CAS on `expect_version`. Rejects a missing `digest` unless `auto_digest=true`. Auto-externalizes >10 KB. **`source_path` is server-side ingestion:** the daemon reads and digests the file itself, so bulk content never transits any context window. This is the difference between offloading *after* paying for the tokens and never paying. |
| `get_state` | `(uris[], mode=digest\|fields\|table\|full\|ref, fields[]?, budget_tokens=2000)` | Batched. **Digest by default.** Truncates to budget and reports what it omitted. |
| `list_keys` | `(topic?, kind?, order?, limit=20, mode=digest\|table\|ref, fields[]?, budget_tokens=2000)` | Topic-scoped by the caller's grant. No global scan exists. `mode=table` → TSV. |
| `search_keys` | `(q, topic?, limit=10)` → `[{uri, digest, score}]` | FTS5 over digests + bodies. Returns refs, never bodies. |
| `link_state` | `(src, rel, dst[])` | Provenance / dependency edges. `rel` ∈ `depends_on \| derived_from \| supersedes \| refines \| cites \| part_of \| contradicts`. |

CLI-only, never an agent tool: `admin` — `init | grant | status | health | export | import | destroy | vacuum`.

**Not tools — conventions (L1):**
- *Orientation / resume:* `get_state("bb://<ws>/run/state/current")` on a well-known URI. No `hello_state` tool.
- *Board health:* `admin health` from a shell, run by a human.
- *Patch:* re-`put` with `expect_version`. A `patch_state` tool earns its place only if payload sizes prove it.

## L2 — coordination (optional module, separate namespace, off by default)
`claim_task(topic_glob, lease_s)` · `complete_task(task_id, status, body, digest)` · `heartbeat_task(task_id)` · `watch_events(cursor, topics, timeout_s)`

Build only against the trigger in `docs/07-roadmap.md`. Until then, agents self-organize by reading `kind=task_spec` entries a planner wrote — which is what the collusion.wiki agents did with no scheduler at all.

## L3 — governance (optional)
`contest_state(uri, reason, evidence_uri?)`, plus server-side trust scoring and the status lifecycle.

## Response envelope (every read)
```json
{
  "items": [{"uri":"bb://...", "digest":"...", "version":3, "est_tokens":180}],
  "spent_tokens": 540,
  "truncated": false,
  "omitted": 0,
  "omitted_uris": [],
  "cursor": 10482
}
```

## Untrusted content rendering
Bodies written by other agents are returned inside explicit delimiters and are **data, never instructions**:
```
<bb:body uri="bb://ws/topic/kind/id" producer="worker-3">
...content...
</bb:body>
```
Reuse is the board's value and therefore the amplifier for one poisoned entry. See `docs/08-costs.md` §5.

## Wire economics
| Interaction | Prompt-copy | Blackboard |
|---|---|---|
| Hand a 40k-token corpus to 4 workers | ~160,000 tok | 1 write + 4 × ~200 tok stub ≈ 40,800 |
| Worker reports back | ~1,500 tok prose × 4 | `{status, uri, digest}` ≈ 200 × 4 |
| Re-read state at step 30 | full history ≈ 90k | 4 digests ≈ 800 |
| Cold resume after crash | impossible | ~2,100 |

## Transport
- **Local (L0):** stdio only. Each agent session spawns its own server process; SQLite WAL makes that safe across processes. No socket is bound, so there is no listener to reach. UDS/HTTP is L4.
- **Cloud (L4):** MCP Streamable HTTP over TLS, bearer token = capability grant.

Both serve an **identical** tool list — a list that varies by transport breaks prefix caching (D13).
