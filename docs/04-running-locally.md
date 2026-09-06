# Running it locally

**For:** anyone installing it. Covers setup, connecting an agent, what is stored where, the security posture, and what happens when things go wrong.


## Terms used on this page

*(Project-wide vocabulary — entry, digest, workspace, topic — is in the [README](../README.md#vocabulary).)*

| Term | Meaning |
|---|---|
| **CAS (compare-and-swap)** | Write only if the entry is still at the version you last read; otherwise the write is rejected. Replaces locking. |
| **TTL (time to live)** | How long something stays valid before it expires on its own. |
| **WAL (write-ahead logging)** | A SQLite mode that lets many readers work while one writer writes. |
| **LRU (least recently used)** | A cleanup rule: discard whatever has gone longest without being read. |
| **UDS (Unix domain socket)** | A local-only connection between processes on one machine. Not built; stdio is used instead. |
| **MCP (Model Context Protocol)** | The vendor-neutral standard by which an AI agent connects to an external tool. |

## Install & run (Requirement 4 — target: under 60 seconds, one command)
```bash
uvx blackboard-mcp init --workspace acme-audit     # creates ~/.blackboard/acme-audit.db + schemas
uvx blackboard-mcp serve --workspace acme-audit    # UDS at ~/.blackboard/bbd.sock
uvx blackboard-mcp grant --role planner  --topics '**'                 # prints token
uvx blackboard-mcp grant --role worker   --topics 'tasks/car/**,domain.automotive/**'
uvx blackboard-mcp status                          # health, entry count, size, trust distribution
uvx blackboard-mcp export --out run.jsonl          # portable dump
uvx blackboard-mcp destroy --workspace acme-audit  # clean disconnect (Requirement 4)
```

`--ephemeral` runs entirely in `:memory:` with a JSONL sidecar for throwaway experiments.

## Wiring into Claude Code (`.mcp.json`, project-scoped)
```json
{
  "mcpServers": {
    "blackboard": {
      "command": "uvx",
      "args": ["blackboard-mcp","serve","--stdio","--workspace","acme-audit"],
      "env": { "BB_TOKEN": "${BB_PLANNER_TOKEN}", "BB_ROLE": "planner" }
    }
  }
}
```
Worker sessions get a different `BB_TOKEN` with a narrower `topic_glob`. Same server binary, different authority — that is the whole isolation story (D10, Q15).

## Wiring into anything else (Requirement 9)
Any MCP client: same stdio command. Non-MCP agents: `--http --bind 127.0.0.1:8787` and call the REST mirror (`GET /v1/entry/...`, `POST /v1/put`). The tool semantics are identical; MCP is a transport, not a dependency.

## Directory layout
```
~/.blackboard/
  acme-audit.db            SQLite (WAL: -wal, -shm alongside)
  artifacts/<aa>/<sha256>  content-addressed blobs (Decision 7)
  schemas/*.json           registered JSON Schemas
  (event log lives in the DB; read it with `blackboard-mcp events`)
```

## Local security posture (Requirement 8)
- **No socket is bound at all.** The Layer 0 — the store transport is stdio: each agent session spawns its own
  server process, and SQLite WAL makes concurrent processes safe. There is nothing to reach
  over the network, which is a stronger posture than binding to loopback.
  A Unix-domain-socket / HTTP listener is **Layer 4 — the cloud**, alongside the Postgres driver.
- **No outbound network calls, ever.** No telemetry. Asserted by `tests/test_local_posture.py`.
- File modes 0600; artifacts directory 0700.
- Token hashes stored, not tokens.
- Optional `--encrypt` (SQLCipher) for sensitive workspaces.
- Sandbox variant: run `bbd` in a container with a single bind-mounted volume and `--network none`; agents reach it over the mounted UDS.

## Operational routine
- **Backup:** `sqlite3 db ".backup snap.db"` — safe under WAL, no quiesce.
- **Health:** `admin health` → dangling URIs, expired leases, contested set, trust histogram, size, Board Health Score.
- **Compaction:** off by default (Decision 12). Enable with `--compact-threshold 5000` once a workspace is large.

## Failure modes and their handling
| Failure | Handling |
|---|---|
| Agent dies mid-task | Lease expires → reaper requeues. No lock held. (Decision 5) |
| Two agents write the same entry | CAS `expect_version` → one gets 409 with the current version and re-reads. |
| Worker writes garbage that validates | Trust score drops on provenance/coherence; planner gates at 0.80; any agent can `contest_state`. (Decision 8) |
| Board grows unbounded | TTL + pin + LRU demote-to-cold. Never destructive. (Decision 12) |
| DB corruption | `entry_history` is append-only; artifacts are content-addressed; `export`/`import` round-trips. |
| Disk full | Writes fail loudly with a typed error; agents are instructed to stop, not to improvise. |
