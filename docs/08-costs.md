# What the Blackboard Actually Costs You

This is the `Coordination Overhead` metric in `docs/06-benchmarks.md`, expanded. It is the number most likely to kill the project.

## 1. Tokens paid whether or not the board helps
- **Tool schema, every turn, every agent.** L0's five tools ≈ 600 tokens/turn (the original eleven were ~1,400). A 40-turn planner + four 10-turn workers ≈ 48k tokens just to *have* the board available.
- **Protocol text in every prefix.** ~900 tokens/agent. Cacheable — but cache write is ~1.25× and cache read is still ~0.1×. Cheap, not free, and only if D13's prefix discipline holds.
- **Round-trip framing.** ~150 tokens of pure envelope per call.
- **Digest generation is *output* tokens.** The one people miss: output costs ~5× input. 50 entries × 200-token digests ≈ 10k output ≈ 50k input-equivalents. The rule that makes reads cheap makes writes expensive.
- **Double reads.** Digest (200) → insufficient → full (3,000) = 3,200 where full alone was 3,000. Above ~30% escalation the ladder is a loss.
- **Orientation tax.** ~2k per agent joining. Trivial on a long task, absurd on a short one.

Crossover heuristic:
```
overhead ≈ (agents × turns × 1.5k) + (calls × 0.15k) + (entries × 1k output-equiv)
savings  ≈ history re-reads eliminated
```
The board wins only when the avoided history is genuinely large.

## 2. Latency you don't get back
- **Every board call is a model turn** — microseconds of DB, seconds of TTFT + generation. Five calls ≈ 5–15s added. The store is never the bottleneck; the round trip is.
- **Lease expiry (L2).** A worker dying at second 5 of a 600s lease blocks that task for 10 minutes. No setting is right for both fast crashes and slow tasks.
- **Single writer.** SQLite serializes writes. Fine at this scale; still real.
- **K8s cold start (L4).** Image pull + warmup can exceed a short task's duration.

## 3. Quality costs — the expensive ones
- **Digest lossiness has no error signal.** The planner decides from 200 tokens. If the digest omitted what mattered, it is confidently wrong and *nothing flags it* — the entry is valid, sourced, and fresh. Structural, not tunable. The largest risk in the design.
- **Decomposition destroys cross-cutting insight.** One agent reading twelve modules sees the pattern *across* them; twelve agents reading one each cannot, by construction. A capability loss, not an overhead. Potentially disqualifying for synthesis and architecture work.
- **Schema straitjacket, discovered late.** Whatever the schema didn't anticipate is gone; re-extraction only works inside the artifact TTL.
- **Stale reads.** CAS protects writes, not reads. An agent can read v3, reason for 40s, and act on state that is now v5. Unaddressed.
- **Trust scores (L3) are heuristics wearing numbers.** `0.83` invites more confidence than it earns.

## 4. Engineering and operational cost
Two store drivers + a conformance suite, schema versioning, three role prompts kept in sync with the tool surface. Debugging goes distributed: a wrong answer has five possible origins across four processes, which makes tracing a prerequisite rather than an enhancement. In cluster: Postgres HA, S3 lifecycle, KEDA, NetworkPolicies, token rotation — real SRE surface for what was a laptop tool.

**This is the main argument for the layering in `docs/08-layers.md`:** most of this cost buys mitigation for failures not yet observed.

## 5. Two risks the design must address in L0
- **Prompt injection via board content.** A board entry containing instruction-shaped text is read by an agent that trusts the board by design — and reuse *amplifies* one poisoned entry across every downstream consumer. **Board content is data, never instructions.** Stated in `skills/blackboard/SKILL.md`; must also be enforced by rendering untrusted bodies inside explicit delimiters.
- **Deletion is genuinely hard.** `entry_history` is append-only and artifacts are content-addressed and deduplicated — both deliberate, both make "delete this data" a real problem. Content is durable on disk, in history, and in backups. If anything regulated touches the board, solve this before L0 ships, not after.

## 6. Net-negative zones
| Situation | Why |
|---|---|
| < ~5 subtasks | Overhead exceeds savings |
| Fits in one context window | Paying to solve a problem you don't have |
| Strongly sequential | No parallelism; digests only lose fidelity |
| Exploratory / ambiguous | You can't decompose what you don't understand yet |
| Single session, no crash risk | Resumption — the best feature — is unused |
| Irreducible context | One large file read end-to-end doesn't decompose |
