# Architecture

The originating questions, the answers the design settles on, and the block
diagrams. Design rationale with rejected alternatives lives in
[`docs/00-decisions.md`](docs/00-decisions.md); measured results in
[`MEASURED.md`](MEASURED.md).

---

## 1. The originating brief

> **Blackboard to store context across Agents.** Inspired by [collusion.wiki](https://collusion.wiki/).

### Requirements

1. Token and context optimization across multiple agents / multiple sessions
2. Home for repeated tasks / instructions / runbooks
3. Agent-to-agent communication benefits — 2+ agents coordinate to complete an instruction faster, with lower token consumption
4. Simple installation, setup, rapid use, disconnect
5. Higher task-execution frequency + latency that is deterministic on plan
6. An internal shared communication protocol that is token-light
7. Context windows stay light
8. Strictly local or sandboxed storage
9. Strictly agent-agnostic, but context-aware calls
10. Simple in design — rule out complexity

### Advantages sought

- Use costlier models (Opus) to **plan and dispatch**, cheaper models (Haiku) to execute atomic tasks, Opus to recombine — with the blackboard as the medium. A separate coordinator handles board logging and updates.
- Token efficiency and optimization.

### Challenges named up front

1. Which metrics to use for the comparison
2. If the board grows without bound, do we need cleanup of older, less-referenced data — and does that cleanup add more complexity than it removes?

### Out of scope, stated at the outset

Number of agents and which model each uses · how the agent ecosystem is built and organized · KV-cache optimizations · what may be written to the board (literally anything) · how agents connect via MCP or other protocols.

---

## 2. The fifteen questions

Full answers with reasoning: [`docs/01-answers.md`](docs/01-answers.md). Condensed here.

| # | Question | Answer |
|---|---|---|
| **Q1** | Are two Claude/Gemini sessions different agents with independent memory and KV cache? | **Yes, fully.** Separate request streams, contexts, KV caches. They share weights, nothing else. *Nuance:* prompt caching is per-**prefix**, not per-session, so a byte-identical protocol prefix is cheaper for the second agent that uses it. |
| **Q2** | How is common information shared across them? | Only via an external addressable medium. Ranked: shared durable store (this design) > prompt hand-off (pays for the payload N times) > raw filesystem (no schema, version, or atomicity). |
| **Q3** | When Claude auto-spawns sub-agents, how do they communicate? | Strictly hierarchically. Parent → child by prompt copy, child → parent by final report. **Siblings never talk.** The parent is both a bottleneck and a token amplifier. |
| **Q4** | Is that internal communication a token exploit? | **Yes** — the core inefficiency. Fan-out is `O(k·C·d)`; the parent re-reading its own history is `O(N²)`. The board replaces the copy with a URI: fan-out drops to `k·(stub + slice)`, fan-in to `{status, uri, digest}` ≈ 200 tokens. |
| **Q5** | Can a common blackboard make this `O(1)`? | **Per step, yes; overall, no.** Index lookup was never the bottleneck. The real change is per-turn ingestion: `O(H)` in accumulated history (so `O(T²)` per task) → `O(k·d)`, independent of prior work → `O(T·k·d)`, linear. Say "O(1) per step" and nothing stronger. |
| **Q6** | Do large contexts degrade performance? | Yes, on four axes: cost (linear, paid every turn), latency (prefill + quadratic attention), accuracy (lost-in-the-middle), and distraction (stale reasoning still reads as true). The board fixes the last two as much as the first two — superseded work is *structurally absent*, not merely old. |
| **Q7** | Which storage format? (A tabular / B JSON-BSON / C KV / D graph / E prose-binary) | **Canonical JSON in KV namespaces (B+C) at rest, rendered per shape at read, relations in an edge table (D).** TSV (A) adopted as a *render mode* — measured **44.6% smaller** than JSON for 30 homogeneous rows. BSON rejected: forces BLOB, kills SQL JSON ops, saves zero *tokens*. Prose (E) rejected as a contract but kept as the mandatory digest. Binary rejected: needs a decode round trip. |
| **Q8** | How does a *single* agent benefit? Does it help the KV cache? | **Yes, but not where it first appears.** A transcript is append-only — offloading a 40 KB result *after* reading it refunds nothing. Benefit comes from **crossing boundaries**: session survival, compaction anchoring, avoided re-derivation, and server-side ingestion (`source_path`) so bulk content never enters a window. KV benefit is conditional on keeping board reads in the **tail**, never the system prompt. |
| **Q9** | Is lossy storage actually lossless compression? | **Lossy on discourse, lossless on the state contract.** Deliberation and dead ends are discarded on purpose; declared schema fields are preserved exactly. **Named risk:** anything the schema failed to anticipate is permanently lost. Mitigated by a free-text escape hatch, TTL-retained source artifacts for re-extraction, and additive versioning. |
| **Q10** | Can a new agent resume mid-run cheaply? ★ How does it behave as if it had been there? | **Yes — measured at 2,679 tokens, flat regardless of board size.** "Being there" decomposes into four things; three are recoverable state (goal + constraints, **decisions and their rationale**, work in flight). The fourth — tacit feel — is not recoverable by any design, and is compensated by making decisions explicit. **Corruption caveat** is answered by layered countermeasures, most of which are L3. |
| **Q11** | Can MCP calls and token consumption be optimized? | **Yes, five levers.** Biggest: the tool-schema surface is re-sent *every turn of every agent* — measured **395 tokens** here against a 600 budget, CI-enforced. Then URIs not payloads; server-side `budget_tokens`; batching (`get_state(uris[])` = one envelope, not N); digest-by-default. Keep the tool list **static** — a varying list defeats prefix caching for everyone. |
| **Q12** | How do two agents with different KV caches split a question and come back? | Planner writes shared context **once** + task specs; workers read only their slice; each writes a result + digest; planner reads the two **digests** (~400 tok) and escalates only on failure. Independent KV caches are irrelevant — they were never going to be shared. |
| **Q13** | Benchmark metrics | TRR, TTS, PEI, SIS — plus the ones that make a result credible: **Task Success Rate as a gate**, **Cost in USD** (Opus/Haiku differ ~15×, so an ecosystem can raise token count while cutting cost 5×), cache hit rate, peak context, rework rate, recovery time, and **coordination overhead** — above ~15% the board is not paying for itself. |
| **Q14** | Is a queue / message broker required? | **No.** A task table with atomic claim-by-lease *is* a queue; a monotonic event log with long-poll *is* pub/sub. Kafka/Rabbit/Redis buy guarantees this workload does not need, at the cost of another daemon. Revisit above ~50 concurrent workers. *(This is L2 — deferred.)* |
| **Q15** | Clean separation between topics (Car vs Guns) | **Three enforced layers:** namespace (`bb://ws/domain.automotive/**`), **capability grant** (the agent's token carries `topic_globs[]`, enforced at the daemon — the load-bearing layer), and a per-topic schema registry. A prompt instruction not to read a topic is advisory; a scoped token is not. |

---

## 3. System architecture

```
+-----------------------------------------------------------------------------------+
|                            PLANNER AGENT (Claude Opus)                            |
|                 - Decomposes into a task DAG & namespaced keys                    |
|                 - Audits outputs, reads DIGESTS not bodies                        |
+------------------------------------------+----------------------------------------+
                                           | writes shared context ONCE
                                           | dispatches URIs, never payloads
                                           v
+-----------------------------------------------------------------------------------+
|                        LOCAL BLACKBOARD ENGINE  (daemon: bbd)                     |
|                                                                                   |
|  +------------------------+  +------------------------+  +---------------------+  |
|  | MCP Gateway (stdio)    |  | Version Manager        |  | Digest + Projection |  |
|  | 5 tools / 395 tokens   |  | expect_version CAS     |  | Engine              |  |
|  | server-side budgets    |  | append-only history    |  | digest|fields|table |  |
|  |                        |  | NO LOCKS               |  | |full|ref           |  |
|  +------------------------+  +------------------------+  +---------------------+  |
|                                                                                   |
|  +------------------------+  +-----------------------------------------------+    |
|  | Capability Enforcement |  | Storage: SQLite WAL (JSON in TEXT)            |    |
|  | topic_globs per token  |  |  + content-addressed artifacts (sha256)       |    |
|  +------------------------+  +-----------------------------------------------+    |
+------------------------------------------^----------------------------------------+
                                           | reads ONLY its slice
                                           | writes result + mandatory digest
                                           v
+-----------------------------------------------------------------------------------+
|                     WORKER AGENTS (Claude Haiku / Gemini Flash)                   |
|          - Scoped token: physically cannot read another lane's topic              |
|          - Escalation ladder: ref -> digest -> fields -> table -> full            |
+-----------------------------------------------------------------------------------+
```

## 4. Layering — what is built, what is deferred

```
   +---------------------------------------------------------------+
   |  L4  CLOUD          Postgres . S3 . HTTP . JWT . Helm . KEDA   |  DEFERRED
   |                     trigger: a second machine needs the board  |  (also needs L2)
   +---------------------------------------------------------------+
   |  L3  GOVERNANCE     Trust score . contest . lifecycle .        |  DEFERRED
   |                     schema registry . curator / compaction     |  trigger: corruption MEASURED
   +---------------------------------------------------------------+
   |  L2  COORDINATION   tasks . DAG . claim . lease . watch        |  DEFERRED
   |                     trigger: agents demonstrably duplicate work|
   +===============================================================+
   |  L1  PROTOCOL       skill prompt . conventions . escalation    |  *** BUILT ***
   |                     ladder . resume recipe . cache discipline  |
   +---------------------------------------------------------------+
   |  L0  STORE          entries . URIs . versions . digests .      |  *** BUILT ***
   |                     projections . artifacts . links . FTS .    |
   |                     event log . scoped tokens . budgets        |
   +---------------------------------------------------------------+
```

Each deferred layer has an **observation** as its trigger, not a date. The
collusion.wiki agents coordinated ~18,000 posts with no schema, no auth, no locks
and no scheduler — so L2 and L3 mitigate failures not yet observed here.

## 5. Token flow — the mechanism being optimized

```
WITHOUT A BOARD                          WITH THE BOARD
---------------                          --------------
Planner ctx: 40k corpus                  Planner writes corpus ONCE -> bb://.../corpus
   |                                        |
   +-- copy 40k --> Worker A  (40k)         +-- "read bb://.../corpus#slice-A" (200 tok)
   +-- copy 40k --> Worker B  (40k)         +-- "read bb://.../corpus#slice-B" (200 tok)
   +-- copy 40k --> Worker C  (40k)         +-- "read bb://.../corpus#slice-C" (200 tok)
   +-- copy 40k --> Worker D  (40k)         +-- "read bb://.../corpus#slice-D" (200 tok)
                                            
   <-- 1.5k prose report x4                 <-- {status, uri, digest} x4  (~200 tok each)
                                            
   Planner re-reads full history            Planner reads 4 DIGESTS (~800 tok)
   every turn -> O(T^2)                     per turn -> O(k*d), flat

   ~166,000 tokens                          ~41,600 tokens
```

## 6. Resume flow — the measured result

```
   Session 1 dies at 60% (having burned 20k ... 400k tokens -- it does not matter)
        |
        |  board holds: run/state/current, task frontier, decisions + rationale
        v
   Session 2 (cold, no memory) runs the documented recipe:

     get_state("bb://<ws>/run/state/current", mode=full)   ~ goal, constraints, phase
     list_keys(topic="tasks.**", mode=table)               ~ frontier as TSV
     list_keys(kind="decision", order=recency, limit=10)   ~ why things are as they are
        |
        v
   OPERATIONAL at 2,679 tokens -- and FLAT as the board grows:

     board 10,506 tok -> resume 2,679  (25.5%)
     board 229,566    -> resume 2,679  ( 1.2%)
     board 886,746    -> resume 2,679  ( 0.3%)
```

## 7. Topic isolation (Q15)

```
   Token: {ws: acme, topic_globs: ["domain.automotive/**","tasks.car/**"], caps:[read,write]}
                                  |
                                  v
   get_state("bb://acme/domain.automotive/fact/brake")  --> ALLOWED
   get_state("bb://acme/domain.armaments/fact/barrel")  --> FORBIDDEN (at the daemon)
   list_keys(topic="**")                                --> armaments rows NEVER LISTED
   search_keys("tungsten")                              --> armaments hits FILTERED OUT

   Enforcement is in the daemon, from the token. Never from a request parameter,
   never from the agent's prompt. A denial does not reveal whether the entry exists.
```

## 8. Data model

```
   entry ---------- uri (PK) . version . digest (MANDATORY) . body | artifact_uri
     |              body_hash . est_tokens . producer . sources . status
     |
     +-- entry_history   append-only; nothing is destructively overwritten
     +-- link            src --rel--> dst   (depends_on, derived_from, supersedes,
     |                                       refines, cites, part_of, contradicts)
     +-- event           append-only log; L2 consumes it via watch
     +-- grant           token_hash . topic_globs . caps
     +-- entry_fts       FTS5 over digests + bodies

   bb://<workspace>/<topic>/<kind>/<id>[@<version>]
   bb-artifact://sha256/<hex>            content-addressed: dedup + integrity + immutability
```

## 9. Deviations from the original blueprint

Fifteen, each marked inline in [`BLUEPRINT.md`](BLUEPRINT.md) with a reason and a
reversal cost. The three defended hardest:

| Δ | Change | Why |
|---|---|---|
| **Δ1** | `acquire_lock`/`release_lock` → CAS + leases | An LLM that hits a rate limit, exhausts its context, or skips a step holds that lock forever. Locks need a liveness guarantee LLM sessions do not have. |
| **Δ2** | V-Score → multi-signal Trust Score | `w₁·schema + w₂·type + w₃·null` is ≈always 1.0 — it cannot detect confidently-wrong, well-formed output, which is the failure it exists for. |
| **Δ3** | Benchmark numbers removed | "185k → 22k tokens, 4.7× speedup" had no run behind it. `MEASURED.md` carries only numbers a test produced. |
