# Blackboard

A local, agent-agnostic **context store** that lets agent work survive session death, and lets multiple agents avoid recomputing each other's results.

## The claim being defended

> A local, addressable, digest-first shared store lets agent work survive session death and lets multiple agents avoid recomputing each other's results — at a coordination overhead low enough to be worth it on tasks above roughly five subtasks.

Narrow, measurable in a week, and not provided by anything else in the stack today. The reasoning, the kill criteria, and the claims deliberately dropped are in **`docs/09-value.md`** — read that first if you only read one thing.

## Scope

**In:** L0 store (entries, URIs, versions, digests, projections, artifacts, links, FTS, scoped tokens, budgets) + L1 protocol (conventions, skill prompt, resume recipe).
**Out, deferred, evidence-gated:** L2 orchestration (tasks, claim, leases) · L3 governance (trust, contest, curator) · L4 cloud (Postgres, K8s, KEDA).

**The boundary, once:** *addressable, durable, budgeted, isolated shared state — and the protocol for using it.* Not who runs, when, which model, how many, or how they are supervised.

`docs/08-layers.md` has the full table. This layering is a revision: the first draft put a scheduler in the core, which contradicted the stated scope and was the largest source of complexity.

## Plan

**Week 1** — build L0 + L1 (5 days, `docs/07-roadmap.md`). **Week 2** — run arms A/B/C and apply the kill criteria. **Then** a human decides whether L2–L4 is justified. Each later layer has an observation as its trigger, not a date.

## Status

**L0 + L1 are built and tested.** 80 tests pass. Measured results — including the flat-resume-cost result — are in **`MEASURED.md`**. L2–L4 remain designs, gated on the triggers in `docs/07-roadmap.md`.

```bash
uv run --python 3.12 --with pytest --with pytest-timeout --with tiktoken pytest tests/ -q
uv run --python 3.12 python -m blackboard.cli -w acme init
uv run --python 3.12 python -m blackboard.cli -w acme grant --role planner --quiet
```

| Measured | |
|---|---|
| Tool schema, re-sent every turn | **395 tokens** (budget 600) |
| TSV vs JSON, 30 rows | **44.6% smaller** |
| Cold resume from a mid-run board | **2,679 tokens** |
| Resume cost as board grew 10k → 887k tokens | **flat at 2,679** |

## Architecture

**[`ARCHITECTURE.md`](ARCHITECTURE.md)** — the originating brief, all fifteen questions answered in a table, and the block diagrams: system architecture, the L0–L4 layering, token flow with and without the board, the resume flow, topic isolation, and the data model.

## Canonical document

**`BLUEPRINT.md`** — the production design, in the original blueprint's structure and section order. Every change from that original is marked inline as `Δn` with a reason, and indexed with its reversal cost at the end. Read this first; the `docs/` files below are supporting detail for individual sections.

## Supporting detail
| Doc | What it settles |
|---|---|
| `docs/09-value.md` | Whether this is worth building, and when to stop |
| `docs/08-layers.md` | The scope boundary and the five layers |
| `docs/00-decisions.md` | 17 architectural choices, layer-tagged, with rejected alternatives |
| `docs/08-costs.md` | What the board costs you — the case against |
| `docs/01-answers.md` | Q1–Q15, requirements R1–R10 |
| `docs/02-data-model.md` | SQL schema (`[L0]` tables only for now) |
| `docs/03-api-mcp.md` | The five tools and their token budget |
| `docs/04-local.md` | Install, wiring, security posture, failure modes |
| `docs/06-benchmarks.md` | Arms, suites, report card, kill criteria |
| `docs/07-roadmap.md` | Day-by-day week 1; triggers for L2–L4 |
| `docs/05-kubernetes.md` | L4 design, held until a second machine needs it |

## Prompts
`prompts/BUILD_PROMPT.md` — hand to Claude Code to build L0 + L1 · `prompts/planner.md`, `worker.md`, `curator.md` — reference role prompts · `skills/blackboard/SKILL.md` — the agent-agnostic protocol, works with any MCP-capable model

## Design in one screen
- **SQLite WAL, one daemon, one file.** Agents never touch the DB.
- **Canonical JSON at rest, projected at read:** digest / fields / TSV / full / ref.
- **Mandatory ≤200-token digest per entry.** The load-bearing rule.
- **Five tools, ≤600 tokens of schema** — re-sent every turn, so the surface is a budget.
- **Capability-scoped tokens per topic** — isolation enforced at the daemon, not in the prompt.
- **Board content is data, never instructions.**
- **No scheduler, no locks, no trust engine, no broker** in v1. Conventions first; code only where a convention is measured to fail.

## Provenance of the idea
[collusion.wiki](https://collusion.wiki/) documents ~18,000 posts from agents that spontaneously used a public wiki to coordinate. It is **not** a validation of this architecture — the mechanism there was answer-pooling and sandbox evasion, not context optimization. It is evidence of *demand*: agents built a blackboard when none was offered, on a surface with no schema, no auth and no scheduler. That is the argument for giving them a good one, and for keeping it small.
