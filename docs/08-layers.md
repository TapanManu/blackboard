# Scope Layering — what is the project, and what is not

Revised after reviewing collusion.wiki. The finding that forced this: ~18,000 agent posts coordinated successfully on a plain wiki with **no schema, no auth, no locks, no coordination primitives**. Protocol emerged from convention. Every mechanism in the original design was a mitigation for a failure that has not been observed here yet.

Correction to my own earlier draft: `claim_task`, the `task` table, leases, the reaper, and KEDA queue-depth scaling are **orchestration**. The stated out-of-scope says this project "does not determine no of agents / how the ecosystem is built." Putting a scheduler in the core contradicted that, and it was the single largest source of complexity.

## The layers

| Layer | Contents | In scope? | Build when | Effort |
|---|---|---|---|---|
| **L0 — Store** | Entries, URIs, versions, digests, topics, artifacts, append-only history, event log, scoped tokens, FTS | **Yes — this is the project** | Now | 4–5 days |
| **L1 — Protocol** | Skill prompt, naming conventions, read-escalation ladder, resume recipe, reference role prompts | **Yes — non-optional** | Now, with L0 | ~1 day |
| **L2 — Coordination** | Tasks, DAG, claim, lease, heartbeat, watch | Optional module, separate tool namespace | When two agents demonstrably duplicate work | 3–4 days |
| **L3 — Governance** | Trust scoring, contest, status lifecycle, schema registry enforcement, curator/compaction | Optional module | When corruption is *measured*, not anticipated | 1 week |
| **L4 — Cloud** | Postgres driver, S3 artifacts, HTTP transport, JWT/JWKS, Helm, KEDA, OTel | Optional deployment target | When a second machine actually needs it | 1 week |

**Ship L0 + L1. Measure. Stop there if the numbers don't justify more.**

## Why L1 is not optional

A store without a usage protocol is SQLite with extra steps. Every win in the collusion.wiki case came from *convention* — timestamps, cohort IDs, round numbers, `ZZZ` backup pages — invented by the agents on top of a dumb surface. The conventions were the product; the wiki was incidental.

So L1 ships as text, not code: the skill prompt, the URI naming scheme, the digest rule, the escalation ladder, and the resume recipe. Costs almost nothing, carries most of the value.

## Conventions before code

Things that were originally tools and are now **conventions** in L1:

| Was | Now |
|---|---|
| `hello_state()` orientation tool | `get_state("bb://<ws>/run/state/current")` on a well-known URI, documented in the skill |
| Board Health Score endpoint | `admin health` CLI, run by a human, not an agent tool |
| Mandatory digest enforced by server | Enforced by server (cheap), but *authored* by convention — the rule matters more than the check |
| Task assignment | Agents self-organize; the planner writes `task_spec` entries and workers read them. No scheduler. |

Every convention that proves insufficient in practice earns promotion to code. That is the promotion path, and the direction is one-way and evidence-gated.

## L0 tool surface — five tools

| Tool | Purpose |
|---|---|
| `update_state(uri, body \| source_path, digest, expect_version?, sources[]?)` | Write. CAS via `expect_version`. Auto-externalize >10 KB. `source_path` = server-side ingestion: bulk content never enters a context window. |
| `get_state(uris[], mode=digest\|fields\|table\|full\|ref, fields[]?, budget_tokens)` | Batched read, digest by default, server-side budget. |
| `list_keys(topic?, kind?, order?, limit, mode, budget_tokens)` | Scoped listing. `mode=table` → TSV. |
| `search_keys(q, topic?, limit)` | FTS over digests + bodies. Returns refs. |
| `link_state(src, rel, dst[])` | Provenance edges. |

~600 tokens of tool schema instead of ~1,400. **Measured at 395** (see `MEASURED.md`). Since schemas are re-sent every turn, that alone is ~800 tokens × turns × agents saved before anything else happens.

L2 adds `claim_task / complete_task / heartbeat_task / watch_events`. L3 adds `contest_state`. Both in separate namespaces, both disableable, neither loaded by default.

## What survives from the original design, and why

| Kept in L0 | Justification |
|---|---|
| Addressable URIs + topics | The wiki's page names. Minimum viable primitive. |
| Mandatory digest | The single highest-leverage rule; makes the board browsable at constant cost. |
| Append-only history | Deletion destroys provenance; the wiki agents built `ZZZ` backup pages for exactly this reason. |
| Content-addressed artifacts | Free dedup + integrity; ~40 lines. |
| Projected reads (digest/TSV/full) | Directly attacks the metric being optimized. Rendering, not storage. |
| `expect_version` CAS | A parameter, not a tool. ~10 lines. Prevents silent lost updates. |
| Scoped tokens | Topic isolation (Q15) must be enforced, not requested. The wiki being public is why it was shut down. |
| Event log | Cheap append; enables L2 later without a schema migration. |

| Deferred | Deferred because |
|---|---|
| Task queue, leases, reaper | Orchestration — out of stated scope. |
| Trust scoring (6 signals) | Mitigates unobserved corruption. Ship when measured. |
| Schema registry enforcement | Start with conventions; formalize the shapes that stabilize. |
| Contest / status lifecycle | Depends on trust. |
| Curator / compaction | Already threshold-gated; nothing reaches the threshold in week one. |
| Postgres / K8s / KEDA / Helm | No second machine yet. |

## The boundary, stated once

**In scope:** addressable, durable, budgeted, isolated shared state — and the protocol for using it.
**Out of scope:** who runs, when they run, which model, how many, and how they are supervised.

---

# Appendix — Full layer manifest

Every item in the design, assigned. Nothing is unassigned; if it is not listed here it is not in the project.

## L0 — Store · **build now** · 4–5 days · the project

**MCP tools (5)** — `update_state` · `get_state` · `list_keys` · `search_keys` · `link_state`

**CLI (not agent tools)** — `init` · `serve` · `grant` · `status` · `health` · `export` · `import` · `destroy` · `vacuum`

**Tables** — `entry` · `entry_history` · `link` · `event` · `grant` · `entry_fts`

**Modules** — `store/base.py` (interface) · `store/sqlite.py` · `uri.py` · `tokens.py` · `render.py` · `artifacts.py` · `server.py` · `cli.py`

**Features**
- `bb://ws/topic/kind/id@version` addressing; `topic_glob` matching
- Five render modes: `digest | fields | table (TSV) | full | ref`
- Mandatory ≤200-token digest; server-generated fallback with `digest_generated`
- Content-addressed artifact offload at 10 KB (`bb-artifact://sha256/…`)
- **Server-side ingestion** via `update_state(source_path=…)` — the daemon reads/hashes/digests the file; only `{uri, digest}` returns to the agent
- `expect_version` CAS → 409 with current version
- Server-side `budget_tokens` with `truncated` / `omitted_uris` reporting
- FTS5 over digests + bodies
- Append-only `entry_history`; nothing destructively overwritten
- Topic-scoped capability tokens (`workspace`, `topic_globs[]`, `caps[]`)
- `<bb:body>` delimiters — board content is data, not instructions
- Append-only `event` log (written now, consumed by L2 later)
- stdio + Unix domain socket; loopback only; zero outbound connections

**Decisions** — D1 · D2(SQLite half) · D3 · D4 · D6 · D7 · D9 · D10 · D14 · D15 · D16 · D17
**Questions answered** — Q1 · Q2 · Q5 · Q6 · Q7 · Q8 · Q9 · Q10(mechanism) · Q11 · Q15
**Requirements** — R1 · R2 · R4 · R6 · R7 · R8 · R9 · R10

**Exit tests** — glob negatives · TSV ≥35% smaller than JSON · concurrent CAS yields exactly one 409 · cross-topic read denied by daemon · zero egress asserted · resume < 3k tokens

**Explicitly excluded** — scheduler · locks · trust engine · message broker · Postgres

**Dormant but present** — `entry.trust` (0, unused until L3) · `entry.status` (only `accepted` until L3)

## L1 — Protocol · **build now, with L0** · ~1 day · non-optional

Ships as **text, not code**.

- `skills/blackboard/SKILL.md` — the agent-agnostic protocol
- `prompts/planner.md` · `prompts/worker.md` · `prompts/curator.md` (reference)
- URI naming scheme and the `kind` vocabulary (`task_spec | result | decision | fact | artifact_ref | runbook | summary | state | question`)
- Well-known URIs — `bb://<ws>/run/state/current`
- Read-escalation ladder — `ref → digest → fields → table → full`
- Resume recipe (~2k tokens to operational standing)
- Digest authoring guidance ("write for a reader who decides from the digest alone")
- Citation rule; never-overwrite-another's-entry rule
- Cooperative claiming convention (no scheduler)
- Prompt-cache prefix discipline
- "When NOT to use the board" thresholds

**Decisions** — D13 · convention halves of D4 and D16
**Questions** — Q3 · Q4 · Q8(cache mechanism) · Q10(resume recipe) · Q12
**Requirements** — R2 · R3 · R5 · R9
**Excluded** — any enforcement code. Conventions that fail get promoted to L0/L2, one way, evidence-gated.

## L2 — Coordination · deferred · 3–4 days

**Trigger:** two agents measurably duplicate work **and** the cooperative `task_spec` convention proved insufficient.

**Tools (4)** — `claim_task` · `complete_task` · `heartbeat_task` · `watch_events`
**Tables** — `task` · `task_dep`
**Features** — atomic claim-by-lease SQL · TTL leases + reaper · DAG dependency gating · priority and capability matching · `attempts` / `max_attempts` · long-poll on the `event` cursor
**Decisions** — D5 · D11
**Questions** — Q12(mechanized) · Q13(PEI) · Q14
**Why deferred** — orchestration; contradicts the stated out-of-scope

## L3 — Governance · deferred · ~1 week

**Trigger:** corruption or confidently-wrong entries **measured** in a real run; or a workspace crosses ~5k entries / ~50 MB.

**Tools (1)** — `contest_state`
**Tables** — `producer_stats` · `schema_reg` (enforcement)
**Columns activated** — `trust` · `trust_parts` · `confidence` · full `status` lifecycle
**Features** — six-signal Trust Score · lifecycle `proposed → accepted → contested → superseded → stale → tombstone` · blast-radius recursive CTE · Board Health Score · JSON Schema enforcement at write · Curator rollups with `derived_from` · TTL / pin / LRU demote-to-cold (never delete)
**Decisions** — D8 · D12
**Questions** — Q9(schema-loss mitigation) · Q10(corruption countermeasures) · Q13(SIS)
**Why deferred** — mitigates failures not yet observed

## L4 — Cloud · deferred · ~1 week

**Trigger:** a second machine actually needs the board.

**Components** — `store/postgres.py` (same conformance suite) · `S3Artifacts` · MCP Streamable HTTP transport · JWT/JWKS verification · Helm chart · distroless Dockerfile · CloudNativePG cluster · NetworkPolicy default-deny · PDB · ResourceQuota · per-workspace token budget → `429 BUDGET_EXHAUSTED` · Prometheus metrics · OTel task spans · Grafana dashboard
**Depends on L2** — the KEDA `ScaledJob` on `blackboard_tasks{state="ready"}` is meaningless without a task queue
**Decisions** — D1(same-image) · D2(Postgres half)
**Questions** — Q13(metric plumbing) · Q15(namespace isolation)
**Why documented now** — so L0's `Store` interface is shaped correctly on day one. Not so it gets built.

## L∞ — never in scope

Not deferred. **Out**, permanently, by design:

- How many agents run, and which model each uses
- How the agent ecosystem is composed, supervised, or routed
- What content agents choose to write — literally anything may be written
- Vendor KV-cache internals and provider-side optimizations
- MCP wire-protocol design; how agents connect to anything
- Business logic inside agent tools
- Cross-organization or multi-tenant SaaS operation

**The boundary, once more:** in scope is *addressable, durable, budgeted, isolated shared state — and the protocol for using it.* Out of scope is *who runs, when, which model, how many, and how they are supervised.*
