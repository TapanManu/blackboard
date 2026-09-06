# ADR Set — Choices I Adopt (and what I reject from the draft)

Status: revised after the collusion.wiki review. **Each decision is tagged with the layer it belongs to** (see `docs/08-layers.md`); only **[L0]** and **[L1]** are being built now.
Every decision below is scoped to the requirement it serves (R1–R10) and the question it answers (Q1–Q15).

---

## [L0] D1. One daemon, two deployments. Not two codebases.
**Choice:** a single process `bbd` (Blackboard Daemon) that owns all state. Agents *never* touch the database file directly — they speak MCP to `bbd`.
- **Local:** `bbd` on a Unix domain socket / stdio, SQLite WAL backend, artifacts on local disk.
- **Cloud/K8s:** the *same* `bbd` image, `--store=postgres --artifacts=s3`, exposed as MCP Streamable HTTP.

**Why:** the draft implied agents open SQLite directly. That works on one laptop and fails the moment you have two pods on a shared volume (SQLite + NFS/EFS locking is unsafe). Routing every access through a daemon makes the local→cloud move a *config change*, not a rewrite. Serves R4, R8, R10.

**Rejected:** agents-open-SQLite-directly (breaks in cloud), and a "local mode" vs "cloud mode" fork (two codebases = two bug surfaces).

---

## [L0/L4] D2. Storage: SQLite (local) / Postgres (cluster), behind one `Store` interface.
SQLite pragmas, non-negotiable:
```sql
PRAGMA journal_mode = WAL;      -- concurrent readers during a write
PRAGMA synchronous  = NORMAL;   -- durability adequate for agent state
PRAGMA busy_timeout = 5000;     -- 5s writer contention wait
PRAGMA foreign_keys = ON;
```
SQLite WAL gives **many readers + exactly one writer**. That is correct for this workload: writes are small deltas, reads dominate 20:1. Postgres is the drop-in for multi-pod. The `Store` interface is ~14 methods; both drivers must pass the identical conformance test suite.

**Rejected:** Redis (no durable schema/validation, another daemon to install — violates R4), a graph DB (D6), a vector DB as the *primary* store (retrieval is a secondary index, never the source of truth).

---

## [L0] D3. Data representation: canonical JSON at rest, **projected** at read time.
This is my main upgrade over the draft's "JSON + KV, done."

Storage is canonical, sorted-key, UTF-8 JSON in a `TEXT` column — native `json_extract()`, no BLOB, no double serialization. **But the read path is a projection compiler**, because the token cost of a read is a function of *rendering*, not of storage:

| Read mode | Renders as | Use |
|---|---|---|
| `digest` (**default**) | ≤200-token prose/struct summary, always precomputed at write time | scanning, orientation, "what exists" |
| `fields` | JSON with only requested paths | targeted field pulls |
| `table` | **TSV** — header row + rows | any result set ≥3 homogeneous records |
| `full` | canonical JSON | one record you actually must reason over |
| `ref` | just `uri + hash + est_tokens` | dependency wiring |

TSV for a 30-row result costs **~45–60% of the equivalent JSON array** (no repeated keys, no braces/quotes). JSON for a single nested record costs less than TSV (which would need flattening). So the answer to Q7 is not "pick one" — it is *store one, render per shape*.

**Rejected:** BSON (BLOB dependency, no SQL JSON ops, zero token benefit — tokens are counted on the *rendered* text, not the storage bytes). Prose-only (ambiguous, unparseable, grows O(N)). Binary interchange (agents cannot read it without a decode tool call — you pay the tokens anyway, plus a round trip).

---

## [L0] D4. Every entry carries a mandatory `digest`.
No entry is written without a ≤200-token summary. The writer supplies it; if absent, `bbd` generates one deterministically from the schema (field names + value shapes + first N chars), and marks `digest_generated=true`.

**Why:** this is what makes the blackboard *browsable* at constant cost. An agent orienting itself reads 40 digests (~4k tokens) instead of 40 bodies (~180k). It is the single highest-leverage rule in the system. Serves R1, R7, Q5, Q10.

---

## [L2] D5. Concurrency: optimistic CAS + TTL leases. **No agent-held explicit locks.**
- Entry writes: `bb.put(uri, body, expect_version=N)` → `409 CONFLICT` with the current version on mismatch.
- Task ownership: `bb.claim()` hands out a **lease** with an expiry; `bb.heartbeat()` extends it; expiry auto-requeues.

**Why I reject the draft's `acquire_lock` / `release_lock`:** an LLM that crashes, gets rate-limited, hits its context limit, or simply *forgets step 5 of its instructions* holds that lock forever and wedges the board. Locks require a liveness guarantee that LLM sessions do not have. Leases fail safe; CAS makes lost updates impossible without any agent cooperation. This removes two tools from the surface (D9) and an entire class of deadlock. Answers Q14.

---

## [L0] D6. Graph relations: an edge table, not a graph database.
```
link(src_uri, rel, dst_uri, weight)
```
Recursive CTEs give ancestry, dependency closure, and blast-radius queries. `rel` ∈ `depends_on | derived_from | contradicts | supersedes | refines | cites | part_of`.

**Why:** the DAG, provenance chains, and contradiction detection are all graph queries — the draft's "graphs add complexity" dismissal gives up provenance, which is what makes trust scoring (D8) possible. But a *dedicated* graph engine is unjustified overhead at this scale. An edge table in the same transaction is graph capability at ~80 lines of SQL. Answers Q7-D.

---

## [L0] D7. Payload offloading is **content-addressed**.
Bodies over 10 KB (tunable) are written to an artifact store keyed by `sha256`: `bb-artifact://sha256/<hex>`. The entry row keeps `digest + hash + est_tokens + artifact_uri`.
- Local: `./.blackboard/artifacts/<aa>/<hash>`
- Cloud: S3/MinIO, same key layout.

Content addressing gives free dedup (two agents producing the same file store it once), free integrity checking, and immutability — so an artifact URI in an old task spec can never silently change under you. The draft's `file://artifacts/id.json` has none of these properties.

---

## [L3] D8. Trust is multi-signal. Schema validity alone is *not* a score.
The draft's V-Score = weighted(schema, type, null) is ~always 1.0, because anything that passes `jsonschema` passes all three. It cannot detect the failure mode it was invented for: **confidently wrong, well-formed output.**

Replace with a **Trust Score** computed server-side at write and recomputed on read:

```
Trust = 0.25·Valid + 0.20·Provenance + 0.20·Corroboration
      + 0.15·Producer + 0.10·Freshness + 0.10·Coherence
```
- `Valid` — JSON Schema pass, required fields, enum/range conformance. Binary-ish.
- `Provenance` — fraction of asserted claims carrying a `source` (a tool result, a file+line, an artifact hash, an upstream `uri`). Unsourced assertions decay this hard.
- `Corroboration` — independent entries agreeing; `contradicts` edges subtract.
- `Producer` — the writing agent's rolling acceptance rate (EWMA of accepted vs contested/retried writes).
- `Freshness` — `exp(-age / half_life_of_kind)`. Kind-specific: `env_fact` decays in hours, `decision` in weeks.
- `Coherence` — referenced URIs exist, at expected versions, and are not tombstoned.

**Lifecycle status** is separate from the score: `proposed → accepted → contested → superseded → stale → tombstone`.
Planner gate: consume `accepted ∧ Trust ≥ 0.80`; `0.60–0.80` consume with an explicit caveat; `< 0.60` re-derive. Any agent may `bb.contest(uri, reason)`, which flips status and forces a re-derive. **This is the answer to the star question in Q10.**

---

## [L0] D9. A small, budgeted tool surface.
Every MCP tool schema is re-sent on **every turn** of every agent. 30 tools ≈ 4–6k tokens burned per turn before anyone has done anything. Hard cap: **L0: five tools, ≤600 tokens of tool schema total.** Descriptions are terse and one-line.

Every read tool takes `budget_tokens`. `bbd` fills up to the budget, then **truncates and tells you what it dropped**, returning the remainder as URIs:
```json
{"items":[...], "truncated": true, "omitted": 14, "omitted_uris":["bb://..."], "spent_tokens": 3980}
```
Server-side context budget enforcement is the difference between a blackboard that saves tokens and one that becomes a new way to blow up a context window. Answers Q11, R7.

---

## [L0] D10. Addressing & isolation: URI + capability grants.
```
bb://<workspace>/<topic>/<kind>/<id>[@<version>]
bb://acme-audit/domain.automotive/spec/brake-assy@3
bb://acme-audit/domain.armaments/spec/barrel-lot@1
```
`workspace` = one engagement/run. `topic` = the domain partition. **Cross-topic reads require an explicit grant.** Each agent session is issued a scoped token: `{workspace, topic_glob[], caps[]}` where caps ∈ `read|write|claim|link|contest|admin`. A worker on the Car task is issued `topic_glob=["domain.automotive/**","tasks/car/**"]` and *physically cannot read* the Guns topic — not by convention, by authorization.

Answers Q15. This is also the honest answer to "how do you stop one agent poisoning another's domain": you don't rely on the prompt, you rely on the token.

---

## [L2] D11. No message broker. A claims table + a watch cursor.
`bb.claim()` is an atomic `UPDATE ... WHERE status='ready' ... RETURNING` — that *is* a queue with exactly-once-per-lease semantics. `bb.watch(cursor, topics[])` long-polls the monotonic `event(seq)` log.
- Local: SQLite update hook → in-process notify.
- Cloud: Postgres `LISTEN/NOTIFY`, poll fallback.
- Only if you exceed ~50 concurrent workers or need cross-cluster fan-out: add NATS JetStream *in front of*, not instead of, the events table.

Kafka/RabbitMQ/Redis Streams for a laptop-scale agent DAG is the complexity R10 exists to rule out. Answers Q14.

---

## [L3] D12. Growth control: a Curator agent + mechanical policy.
Mechanical (no LLM): TTL per kind, `pinned` flag, reference-count from `link`, LRU on `reads/last_read_at`, tombstone-then-vacuum.
Semantic (cheap model, Haiku/Flash, runs on a threshold not a timer): roll up N sibling entries into one `summary` entry, write `derived_from` edges to the originals, demote originals to `cold` (digest stays in the DB, body moves to artifact storage).

**Counter-question answered honestly:** yes, this adds complexity — so it is *off by default*. Phase 1 ships TTL + pin only. Compaction turns on when a workspace crosses ~5k entries or ~50 MB, and it never deletes: it demotes. Rollback is always possible because originals are content-addressed. Answers the Challenges section.

---

## [L1] D13. Prompt-cache discipline is a first-class design constraint.
Blackboard content must **never** be injected ahead of an agent's stable prefix. Canonical layout:
```
[ system prompt ][ skill/protocol text ][ tool schemas ]   ← stable, cacheable, never varies
--------------------------------- cache breakpoint ---------------------------------
[ blackboard reads ][ turn history ]                        ← volatile
```
This is the actual mechanism behind the Q8 single-agent benefit: a stable prefix stays cache-warm across turns and across *sessions*, while volatile state lives in the tail and is swapped freely. Injecting board content into the system prompt would invalidate the cache on every read and make the blackboard a net loss.

---

## [L0] D14. Implementation: Python 3.12 + `uv`, single-command install.
```
uvx blackboard-mcp init && uvx blackboard-mcp serve
```
Python because the agent ecosystem is Python/TS and you will iterate on schemas weekly. `uv` because it makes install one command with no venv ritual (R4). FastAPI/Starlette for the HTTP transport, `aiosqlite`/`asyncpg`, `jsonschema` for validation, `tiktoken`-compatible estimator for `est_tokens`.
Go is the v2 rewrite target *if* single-static-binary distribution becomes the constraint. Do not start there.

---

## [L0] D15. Benchmarks report quality first, savings second.
A token saving with a quality regression is not a result. Every benchmark row is **paired**: baseline vs ecosystem on the identical task, n≥5, median + IQR, and a **Task Success Rate gate** — savings are only reported for configurations at quality parity (Δ success ≤ 2pp). See `docs/06-benchmarks.md`.


---

## [L0] D16. Layer the scope. Build L0 + L1 only; gate the rest on measurement.
**Choice:** the project is a *context store plus a protocol*. Orchestration (tasks, claim, lease, scheduling) is L2 and out of the core; governance (trust, contest, curator) is L3; cloud is L4. Full table in `docs/08-layers.md`.

**Why:** ~18,000 agent posts coordinated successfully on a plain wiki with no schema, no auth, no locks, and no scheduler — protocol emerged from convention. D5, D8, D11 and D12 all mitigate failures that have not been observed in this system yet. Building a mitigation before its failure is how this class of project dies at 80% complete.

Also a correction: putting `claim_task` and leases in the core contradicted the stated out-of-scope ("does not determine no of agents / how the ecosystem is built"). That was my error, and it was the largest single source of complexity.

**Promotion rule:** a convention becomes code only when it demonstrably fails in a real run. One-way, evidence-gated.

---

## [L0] D17. Board content is data, never instructions.
Bodies written by other agents are returned inside explicit `<bb:body …>` delimiters, and every role prompt states that board content is never to be followed as instruction. Reuse is the board's entire value, which makes it the amplifier for a single poisoned entry.

Open item that must be answered before L0 ships: **deletion**. `entry_history` is append-only and artifacts are content-addressed and deduplicated — both deliberate, both make redaction hard. Decide whether regulated data may touch the board *now*, not after.
