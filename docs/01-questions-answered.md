# The fifteen questions, answered in full

**For:** anyone who wants the reasoning rather than the summary. [Architecture](../ARCHITECTURE.md#2-the-fifteen-questions) has the short version of these same answers.

> **Scope note (revised):** the answers below describe the full design space. Only **Layer 0 — the store (store) + Layer 1 — the protocol (protocol)** are being built now; orchestration, governance and cloud are deferred and held until evidence justifies them. See [Scope: what is built and what is held back](08-scope-and-layers.md) and [Is this worth building — the honest case](10-is-it-worth-building.md).

---


## Terms used on this page

*(Project-wide vocabulary — entry, digest, workspace, topic — is in the [README](../README.md#vocabulary).)*

| Term | Meaning |
|---|---|
| **CAS (compare-and-swap)** | Write only if the entry is still at the version you last read; otherwise the write is rejected. Replaces locking. |
| **TTL (time to live)** | How long something stays valid before it expires on its own. |
| **WAL (write-ahead logging)** | A SQLite mode that lets many readers work while one writer writes. |
| **FTS (full-text search)** | SQLite's built-in text search, used here over summaries and contents. |
| **DAG (directed acyclic graph)** | A dependency tree with no loops — task B waits for task A, and nothing waits on itself. |
| **CTE (common table expression)** | A SQL feature for recursive queries, used here to walk chains of related entries. |
| **UDS (Unix domain socket)** | A local-only connection between processes on one machine. Not built; stdio is used instead. |
| **TRR (Token Reduction Ratio)** | How many fewer tokens an approach uses than the single-agent baseline. |
| **PEI (Parallel Efficiency Index)** | How well the work actually parallelized. 1.0 would be perfect; 0.5-0.7 is realistic. |
| **TSR (Task Success Rate)** | Whether the answer was correct. Used as a gate: a cheaper wrong answer is not a result. |
| **TTS (Time to Solution)** | Wall-clock time from the first prompt to an accepted answer. |
| **KEDA** | A Kubernetes add-on that starts and stops workers based on a metric — here, how many tasks are waiting. |
| **MCP (Model Context Protocol)** | The vendor-neutral standard by which an AI agent connects to an external tool. |
| **TSV (tab-separated values)** | Rows of data with one header line — far cheaper in tokens than JSON for repetitive records. |

## Q1. Are two Claude/Gemini sessions different agents with independent memory and KV cache?
**Yes, fully independent.** Separate request streams, separate context windows, separate KV caches. Two sessions on the same model share *weights*, nothing else. Neither can observe the other's context, scratchpad, or tool results. There is no ambient channel between them.

Nuance worth keeping: **prompt caching is per-prefix, not per-session.** Two sessions that begin with a byte-identical prefix can hit the *same* cached prefix on the provider side. That is not shared memory — neither can read the other's data — but it does mean a shared, stable, canonical protocol prefix (Decision 13) is cheaper for the *second* agent that uses it. That is a real, exploitable property of the blackboard's skill text.

## Q2. If yes, how is common information / subtasks shared?
Only by an external medium both can address. Three mechanisms, ranked:
1. **Shared durable store (the blackboard)** — asynchronous, survives session death, addressable, versioned. This design.
2. **Prompt hand-off** — parent inlines context into the child's opening prompt. Simple, but the payload is copied into N contexts and paid for N times.
3. **Filesystem/repo** — works, but no schema, no versions, no trust, no atomicity, no query.

The blackboard is (3) with a contract: schema, version, provenance, trust, budgeted reads.

## Q3. When Claude auto-spawns sub-agents, how do they communicate?
Strictly **hierarchically, through the parent**. The parent composes a task prompt (a *copy* of the relevant context), the sub-agent runs in a fresh window, and returns a final text report. Siblings never talk directly; there is no lateral channel. Everything flows parent → child (prompt) and child → parent (report).

Consequence: the parent is a bottleneck *and* a token amplifier, which is exactly Q4.

## Q4. Is that internal communication a token exploit? For in-context reads?
Yes — this is the core inefficiency the blackboard removes.

Let `C` = shared context size, `k` = sub-agents, `d` = handoff depth.
- **Prompt-copy fan-out:** total ingested ≈ `k·C` per level, `O(k·C·d)` overall. Every sub-agent pays full freight for context it mostly does not use.
- **Report fan-in:** each child returns prose the parent must ingest; with `k` children over `r` rounds the parent's window grows `O(k·r)` and it re-reads its own accumulated history every turn → the parent alone is `O(N²)` in cumulative tokens over a long run.

With the blackboard: the parent writes the shared context **once** and hands each child a URI. Each child reads only its slice. Fan-out cost drops from `k·C` to `k·(s + C_i)` where `s` is a small stub (~200 tokens) and `C_i` is that child's actual slice. Fan-in returns a `uri + digest`, not a transcript, so the parent's window grows by ~150 tokens per child instead of thousands.

## Q5. Can a common blackboard make this O(1)?
**Precisely stated, yes — but not the way the draft says it.** Two different complexities are being conflated:

- **Storage lookup:** an indexed primary-key fetch is `O(log n)` (B-tree) or `O(1)` (hash). This was never the bottleneck. Nobody's latency problem is SQLite index descent.
- **Context cost — the one that matters:** without a blackboard, an agent's per-turn ingestion is `O(H)` in accumulated history `H`, and `H` grows with every step, so a `T`-step task costs `O(T²)`. With a blackboard, per-turn ingestion is `O(k·d)` where `k` = entries deliberately read and `d` = digest size — **independent of how much work has happened before**. A `T`-step task costs `O(T·k·d)`, i.e. linear.

So the honest claim: **the blackboard converts context cost from quadratic-in-task-length to constant-per-step.** Call it `O(1) per step`, never `O(1) overall`. Overstating this is the fastest way to lose a technical audience.

## Q6. Do large contexts create issues and reduce performance?
Yes, on four axes:
1. **Cost** — linear in tokens, paid every turn.
2. **Latency** — prefill scales with context; attention is quadratic in sequence length. TTFT visibly degrades past ~100k.
3. **Accuracy** — "lost in the middle": retrieval of a fact degrades with distance and with the volume of competing material. More context is not more knowledge.
4. **Distraction** — stale intermediate reasoning, abandoned approaches, and dead tool output stay in the window and actively mislead. A failed attempt from step 4 is still "true-looking" text at step 40.

The blackboard fixes (3) and (4) as much as (1) and (2): only *current, accepted* state is loaded, so superseded reasoning is structurally absent instead of merely old.

## Q7. Which storage format is better? (A tabular / B JSON-BSON / C KV / D graph / E prose-binary)
**Answer: store canonical JSON in KV namespaces (B+C), render per shape at read time, keep relations in an edge table (D).** See ADR Decisions 3 and 6.

| Option | Verdict | Reasoning |
|---|---|---|
| **A. Tabular / TSV** | **Adopted as a render mode** | Best token density for homogeneous rows — no repeated keys. ~45–60% of equivalent JSON. Wrong for nested/heterogeneous records. |
| **B. JSON** | **Adopted as canonical at rest** | Native to function-calling, schema-validatable, `json_extract()` queryable, human-diffable. |
| **B. BSON** | **Rejected** | Forces BLOB, kills SQL JSON ops, requires decode before the model sees anything, and saves zero *tokens* — token count is on rendered text, not stored bytes. |
| **C. KV namespacing** | **Adopted as the addressing layer** | This is the `bb://ws/topic/kind/id` URI. It is orthogonal to the value format, not a competitor to it. |
| **D. Graph** | **Adopted as a secondary index** | Edge table + recursive CTE. Buys provenance, dependency closure, contradiction detection. A graph *engine* is unjustified overhead. |
| **E. Prose** | **Rejected as a contract; retained as `digest`** | Ambiguous and unbounded for state, but unbeatable for the 200-token "what is this" summary. Use it for orientation, never for values. |
| **E. Binary** | **Rejected** | Agents cannot read it without a decode round trip — you pay the tokens plus a tool call. |

Rule of thumb the system enforces: **≥3 homogeneous records → TSV. Nested single record → JSON. Anything a human or planner is scanning → digest.**

## Q8. How does a *single* agent benefit? Does it help the KV cache?
**Yes, but the mechanism is narrower than it first appears, and one common claim about it is false.**

**The false claim first.** The board cannot remove tokens already in your window. A transcript is append-only; if a 40k-token tool result has landed in your context, writing it to an artifact afterwards does not un-read it. You already paid. Within one continuous session, offloading-after-the-fact buys nothing for the current window.

Single-agent benefit therefore comes from **crossing boundaries**, not from compressing a live window:

1. **Session survival** — context limit, crash, or `/clear` no longer destroys progress (Q10). Unambiguous, and unique to the board.
2. **Compaction anchoring** — when a long session is summarized, transcript detail is lost by whatever heuristic the harness uses. Board state survives *verbatim*. The board is a durable anchor that compaction cannot erode.
3. **Avoided re-derivation** — instead of re-reading a file or re-running an analysis later in the session, `get_state` the digest. This is a real within-session win, but only for content already on the board.
4. **Server-side ingestion — the one that makes (3) work from a cold start.** `update_state(uri, source_path=…)` has the *daemon* read the file, hash it, externalize it, and return only `{uri, digest}`. The 40k tokens never enter any context window at all. This is the difference between "offload after paying" (worthless) and "never pay" (the actual win). It is a parameter on an existing tool, not a new one, so it costs nothing in tool-schema budget.
5. **Runbook reuse** — repeated instructions live on the board (Requirement 2), not re-typed and re-tokenized each session.
6. **Sub-agent offloading** — a big result lands in the sub-agent's window, is written to the board, and the parent reads the digest. Real, but this is the multi-agent mechanism wearing a single-agent hat.
7. **Prompt-cache stability (the KV part)** — and here the mechanism must be stated precisely:

The blackboard does not make the KV cache smarter. It makes the cache *hit*. Prompt caching works on an **exact-match prefix**: the moment a byte changes at position `i`, everything from `i` onward is recomputed. If volatile state is injected into the system prompt, every board read invalidates the whole prefix and the cache never pays off. The discipline in D13 — stable protocol prefix first, volatile board reads strictly in the tail — is what converts blackboard usage into a cache-hit-rate improvement instead of a cache-hit-rate disaster. Measure it: `cache_read_input_tokens / total_input_tokens` is a benchmark metric ([How performance will be proven](06-benchmark-plan.md)), and a run where it drops is a design failure, not a tuning issue.

**The honest single-agent caveat:** attaching the board adds ~1,500 tokens (tool schemas + protocol text) to *every turn's* prefix. For one agent, in one window, with no handoff, no compaction and no crash, that is pure cost with nothing on the other side of the ledger. **The single-agent crossover threshold is higher than the multi-agent one**, and it is set by the number of context boundaries the task crosses — not by task size.

## Q9. Is lossy storage actually lossless compression?
No — and the distinction is the useful part. Two channels, compressed differently:

- **Discourse (the reasoning transcript): deliberately lossy, near-total loss.** Deliberation, retries, dead ends. Discarded on purpose; keeping it is the distraction problem in Q6.
- **State (the facts, decisions, artifacts): lossless *against the schema*.** Every field the schema declares is preserved exactly; artifacts are byte-identical and hash-verified.

So: **lossy on discourse, lossless on the state contract.** The risk this creates is real and must be named: the schema defines what is preserved, so *anything the schema failed to anticipate is permanently lost.* Mitigations: (a) every entry keeps a `notes` free-text escape hatch; (b) the source artifact is retained content-addressed for a TTL window, so a re-extraction under a corrected schema is possible; (c) schema changes are versioned and additive.

## Q10. Mid-session stop, new agent in a new session resumes cheaply. Possible? ★ How does it behave like it was there before?
**Yes.** The resume path is a fixed, bounded sequence:

```
bb.hello(agent_id, role)                     -- ~300 tok: workspace manifest, protocol version, topic map
bb.get("bb://ws/run/state/current")          -- ~400 tok: goal, phase, invariants, open questions
bb.query(topic="tasks", status in (ready,in_progress,blocked), mode=table)
                                             -- ~600 tok: TSV of the frontier only
bb.query(kind="decision", order=recency, limit=10, mode=digest)
                                             -- ~800 tok: why things are the way they are
```
**≈2.1k tokens to full operational standing**, regardless of whether the predecessor burned 20k or 400k tokens getting there.

The star question — *why does it behave like it was there before?* — because "being there before" decomposes into exactly four things, and three of them are recoverable state:
- **Goal + constraints** → `run/state/current`. Recovered.
- **Decisions already made and their rationale** → `kind=decision` with `supersedes` edges. Recovered. This is the one naive resume always loses, and it is why fresh agents re-litigate settled questions.
- **Work completed and in flight** → task table + leases. Recovered.
- **Tacit feel for the problem** → *not* recovered, and no design recovers it. Compensated by making decisions explicit rather than implicit. Be honest about this in any writeup.

**Caveat — corrupted or badly organized board corrupts the agent.** Countermeasures, layered:
1. **Schema validation at write.** Malformed never lands.
2. **Trust Score (Decision 8).** Planner consumes `accepted ∧ Trust ≥ 0.80`; `0.60–0.80` with caveat; `<0.60` re-derive.
3. **Status lifecycle.** `contested` entries are excluded from default reads and surfaced to the planner as open questions.
4. **Provenance edges.** Every derived entry links `derived_from`; a contested root marks its descendants `suspect` via a recursive CTE — one query gives blast radius.
5. **Content-addressed artifacts.** Hash mismatch = hard failure, not a silent wrong answer.
6. **Coherence check on resume.** `bb.hello` runs an integrity pass (dangling URIs, version skew, expired leases, contradiction pairs) and returns a **Board Health Score**; below 0.7 the joining agent's first job is triage, not execution.
7. **Append-only history.** Nothing is destructively overwritten; `entry_history` allows rollback to the last-good version.

## Q11. Scope for optimizing MCP protocol / API calls / token consumption?
Substantial, in five places:
1. **Tool-schema surface.** Every tool definition is re-sent every turn. ≤12 tools, ≤1,400 tokens total (Decision 9). Cutting a 6k-token tool surface to 1.4k saves ~4.6k **per turn, per agent** — often the single biggest line item.
2. **URIs instead of payloads.** Pass `bb://…` / `bb-artifact://sha256/…` in arguments; never inline a blob.
3. **Server-side budgets.** `budget_tokens` on every read, with explicit truncation reporting (Decision 9). The server, not the model, enforces the ceiling.
4. **Batching.** `bb.get(uris[])` — one round trip, one tool-result envelope, instead of N. Round-trip overhead is ~80–150 tokens of envelope each.
5. **Digest-by-default.** Full bodies are opt-in. Nothing returns a body you did not explicitly ask for.

Additionally: enable **prompt caching on the protocol/skill prefix** (Decision 13), and keep the MCP server's tool list *static* — a tool list that varies by session defeats prefix caching for every agent.

## Q12. How do two agents with different KV caches work on a common question, split it, and come back?
```
1. Planner decomposes → writes DAG nodes + a shared-context entry, once.
     bb.put(bb://ws/tasks/spec/t1 ...), bb.put(.../t2 ...), bb.link(t2, depends_on, t1)
2. Workers claim independently — atomic lease, no coordination call needed.
     A: bb.claim(topics=["tasks/**"]) → t1     B: bb.claim(...) → t2
3. Each reads ONLY its spec + the referenced inputs. Neither sees the other's scratchpad.
4. Each writes a result entry + a digest, then bb.complete(task_id, result_uri).
5. Planner watches the event cursor, reads the two DIGESTS (~400 tok total),
   checks Trust, and synthesizes. It reads a full body only on a trust failure.
```
Nothing is shared but the board. Independent KV caches are irrelevant — they were never going to be shared, and the design does not need them to be. Where they *do* matter: each worker's stable protocol prefix is cacheable, so a worker pool running many short tasks gets high cache-hit rates on its prefix.

## Q13. Benchmark metrics
Primary:
- **TRR — Token Reduction Ratio:** `1 − (ecosystem_total_tokens / baseline_total_tokens)`. Count *all* agents, all turns, input+output+cache-read, and price them separately.
- **TTS — Time to Solution:** wall-clock, first prompt to accepted final answer.
- **PEI — Parallel Efficiency Index:** `T_serial / (T_parallel × active_workers)`. 1.0 = perfect scaling; realistic target 0.5–0.7.
- **TSR — Task Success Rate:** rubric-graded + deterministic checks. **Gate metric — no savings claim is valid without parity.**

Secondary (the ones that make the result credible):
- **Cost ($)** — the honest headline. Token counts hide that Opus and Haiku differ ~15× in price; an ecosystem can *raise* token count while cutting cost 5×. Report both.
- **Cache Hit Rate** — `cache_read_input / total_input`. Validates D13.
- **Peak Context** — max window occupancy per agent. Proves the O(1)-per-step claim directly.
- **Rework Rate** — retries ÷ tasks. The cost of coordination failure.
- **Board Health / Trust distribution** — mean Trust of accepted entries; % contested.
- **Recovery Time** — tokens and seconds for a cold agent to reach operational standing (Q10).
- **Coordination Overhead** — tokens spent on board I/O ÷ total. If this exceeds ~15%, the blackboard is not paying for itself.

## Q14. Is a queue / message broker required? *(answer applies to Layer 2 — the coordination, which is deferred)*
**No.** A `task` table with atomic claim-by-lease *is* a work queue with the right semantics, and `event(seq)` + long-poll *is* a pub/sub log. SQLite WAL handles the local case; Postgres `LISTEN/NOTIFY` the cluster case. Adding Kafka/RabbitMQ/Redis buys ordering and fan-out guarantees this workload does not need, at the cost of another daemon (violating R4 and Requirement 10). Revisit only above ~50 concurrent workers or cross-cluster fan-out — and then add NATS JetStream *in front of* the events table, not instead of it. See D11.

## Q15. Clean separation between topics (Car vs Guns)
Three enforced layers:
1. **Namespace** — `bb://ws/domain.automotive/**` vs `bb://ws/domain.armaments/**`. Queries are topic-scoped by default; there is no unscoped "list everything".
2. **Capability grant** — each agent session's token carries `topic_glob[]`. A car worker's token does not authorize the armaments topic. Enforcement is at the daemon, not in the prompt. **This is the load-bearing layer** — prompt-level instructions to "not look at" a topic are advisory; a scoped token is not.
3. **Schema registry per topic** — `domain.automotive/spec` and `domain.armaments/spec` are distinct `schema_id`s. A car spec cannot be written into the guns topic; validation rejects it.

Cross-topic work is possible but explicit: a `bridge` entry with `cites` edges to both, written by an agent holding both grants, and it is auditable in the event log.

---

## Requirements coverage

| # | Requirement | How it is met |
|---|---|---|
| R1 | Token/context optimization across agents & sessions | Digest-first reads (Decision 4), budgets (Decision 9), URI passing, artifact offload (Decision 7) |
| R2 | Home for repeated tasks / instructions / runbooks | `kind=runbook` entries, versioned + pinned; agents `bb.get` a runbook instead of re-prompting it |
| R3 | A2A benefits — 2+ agents faster & cheaper | Claim/lease parallelism (Decision 5), digest fan-in, no transcript copying (Q4/Q12) |
| R4 | Simple install / setup / rapid use / disconnect | `uvx blackboard-mcp init && serve`; one config block; `--ephemeral` for throwaway workspaces (Decision 14) |
| R5 | Higher task frequency + deterministic latency | Precomputed digests, indexed reads, bounded response sizes → predictable p95, not model-dependent |
| R6 | Token-light internal protocol | URIs + digests + TSV; a completion signal is `{task_id,status,uri}` ≈ 30 tokens |
| R7 | Light context windows | Server-enforced `budget_tokens`; nothing returns a full body unrequested |
| R8 | Strictly local / sandboxed storage | SQLite + local artifacts, loopback/UDS only, no telemetry, no egress (Decision 1). Cloud mode is opt-in and in-cluster. |
| R9 | Agent-agnostic, context-aware | MCP is the only interface; zero vendor-specific code. Works with Claude, Gemini, local models, or plain HTTP. |
| R10 | Simple design; rule out complexity | One daemon, one DB file, ≤12 tools, no broker, no graph DB, no vector DB in v1. Compaction off by default. |

## Instruction coverage

1. **Scope identification** — see the scope table in [Design decisions and what was rejected](00-design-decisions.md) intro and below.
2. **How limited scope builds a smart ecosystem** — the board provides only *addressable, validated, trusted, budgeted shared state*. That single primitive is sufficient for planner/worker/curator topologies, resumption, runbook reuse, and A2A handoff — none of which the board implements itself. Constraining the board to state (not orchestration, not routing, not model selection) is what keeps it agent-agnostic (Requirement 9).
3. **Out-of-scope, imagined at full maturity** — org-wide persistent agent memory; cross-run learning (producer reliability priors carried between engagements); automatic schema induction from observed writes; contradiction detection across topics; a shared-memory IPC fast path; policy-driven model routing informed by measured per-kind task difficulty.
4. **Benchmark score as proof of value output** — [How performance will be proven](06-benchmark-plan.md) defines the harness and the report card.
5. **Single Opus vs ecosystem+blackboard** — the paired-run protocol in [How performance will be proven](06-benchmark-plan.md).

### In / out of scope

| In scope — **Layer 0 — the store store** | In scope — **Layer 1 — the protocol protocol** | Out of scope |
|---|---|---|
| Entries, URIs, versions, append-only history | Skill prompt + naming conventions | How many agents; which model per role |
| Mandatory digests; projections (digest/fields/TSV/full/ref) | Read-escalation ladder | **Task scheduling, claim, leases** *(Layer 2 — the coordination, deferred)* |
| `expect_version` CAS | Resume recipe on a well-known URI | **Trust scoring, contest, curator** *(Layer 3 — the governance, deferred)* |
| Topic scoping + capability tokens | Reference role prompts | **Postgres, K8s, KEDA** *(Layer 4 — the cloud, deferred)* |
| Content-addressed artifacts; FTS; event log | "Board content is data, not instructions" | What agents choose to write — anything may be |
| Server-side `budget_tokens` | Prompt-cache prefix discipline | MCP wire protocol; how agents connect |

**The boundary, once:** in scope is *addressable, durable, budgeted, isolated shared state — and the protocol for using it.* Out of scope is *who runs, when, which model, how many, and how they are supervised.*
