# Blackboard

**A shared notepad for AI agents.** It runs on your machine, stores what agents
learn, and lets a new agent pick up where a previous one stopped — without
re-reading everything that came before.

---

## The problem

An AI agent reads its entire conversation on every single turn. That transcript
only grows, so a long task gets steadily more expensive:

- **Step 5** — the agent re-reads 8,000 words of history. Cheap.
- **Step 50** — it re-reads 200,000 words. Slow, expensive, and it starts missing
  things buried in the middle.
- **The session ends** — context limit, a crash, a closed terminal — and *all of
  it is gone*. The next agent starts from nothing.

It gets worse with several agents. To hand work to a helper agent, the usual
approach copies the relevant background into the helper's prompt. Four helpers
means paying for that background four times. When they report back in prose, the
coordinator has to read all four reports — and re-read them on every turn after
that.

## The idea

Give the agents a shared place to write things down.

Each note gets an address and a short **summary** (we call it a *digest* — one
paragraph, roughly 150 words, capped at 200 tokens). Agents read summaries by
default and only open the full note when they genuinely need the detail.

So instead of copying a 40,000-word document into four agents' prompts, you write
it to the board once and hand each agent an address. Instead of a coordinator
re-reading four long reports forever, it reads four short summaries.

The measurable result: **the cost of picking up a task stops growing with how
much work came before it.**

## Does it work?

Yes, for the specific thing it was built to do. From the test suite, counted with
a real tokenizer rather than an estimate:

A fresh agent joining a half-finished project needs **2,679 tokens** to know the
goal, the constraints, what is done, what is in flight, and which decisions were
already made and why. That number **does not move** as the project grows:

| Work stored on the board | A fresh agent needs | Share of reading everything |
|---|---|---|
| 10,506 tokens | **2,679 tokens** | 25.5% |
| 229,566 tokens | **2,679 tokens** | 1.2% |
| 886,746 tokens | **2,679 tokens** | 0.3% |

Flat. That flat line is the point of the whole project.

Two other measurements:

| What | Result |
|---|---|
| Table data written as TSV instead of JSON | **44.6% fewer tokens** (30 rows) |
| The tool descriptions agents carry every turn | **395 tokens** (self-imposed limit: 600) |
| Five agents, one task, live A/B | **93.6% less** parent context (36,766 → 2,357 tok), n=1 |

Full detail and the bugs measurement caught: **[Measured results](MEASURED.md)**.

---

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12.

```bash
git clone https://github.com/TapanManu/blackboard.git
cd blackboard
uv venv --python 3.12 && uv pip install -e '.[dev,mcp]'

# create a workspace and an access token for an agent
uv run blackboard-mcp -w myproject init
uv run blackboard-mcp -w myproject grant --role planner --quiet

uv run pytest -q        # 120 tests
```

Connect it to Claude Code by copying `.mcp.json.example` to `.mcp.json`. Any
MCP-capable client works — nothing here is specific to one model or vendor.

**Setting it up properly is [SETUP.md](SETUP.md)** — the prerequisites, the three skills to install,
per-client adapters in [`integrations/`](integrations/), and how to verify. A reachable board that
nobody taught the protocol to gets used badly, which costs more than not having one.

---

## The five things an agent can do

| Tool | What it does |
|---|---|
| `update_state` | Write a note. Requires a summary. Large files are stored outside the note. |
| `get_state` | Read notes by address. Returns summaries unless you ask for more. |
| `list_keys` | List what exists in a subject area. Can return a compact table. |
| `search_keys` | Full-text search. Returns addresses and summaries, never full contents. |
| `link_state` | Record that one note came from, depends on, or contradicts another. |

That is the complete surface. There is deliberately no scheduler, no locking, and
no task queue — see [What we chose not to build](#what-is-built-and-what-is-not).

## Vocabulary

You need six words to read the rest of this repository.

| Term | Meaning |
|---|---|
| **Entry** | One note on the board. Has an address, a version, a summary, and contents. |
| **Digest** | The mandatory short summary on every entry (≤200 tokens). Agents read these first. This is the single most important rule in the system. |
| **Workspace** | One project or engagement. Its own database file. |
| **Topic** | A subject area inside a workspace, e.g. `domain.automotive`. Used to keep unrelated work separated. |
| **Token** | The unit AI models read and are billed in — roughly ¾ of a word. |
| **Context window** | Everything a model can see at once. The scarce resource this project exists to conserve. |

Addresses look like this:

```
bb://myproject/domain.automotive/fact/brake-assembly
    └workspace┘ └───topic─────┘ └kind┘ └────name────┘
```

## How it stays cheap

**Summaries first.** Every entry carries one, and reading returns summaries by
default. Reading 40 summaries costs about 4,000 tokens; reading 40 full entries
could cost 180,000.

**Ask for only what you need.** Five ways to read an entry, cheapest first:
just the address → the summary → specific fields → a compact table → the whole
thing. Start at the left and move right only when you must.

**The server enforces a budget.** Every read takes a token budget. The server
fills up to it, stops, and tells you exactly what it left out. It is not possible
for a read to quietly flood an agent's context window.

**Big files never pass through an agent.** Ask the server to ingest a file by
path and it reads, stores and summarizes it itself — the agent receives an
address and a summary. Reading a 40,000-token file *and then* filing it away
saves nothing; you already paid for it.

**Unrelated subjects cannot leak into each other.** Each agent's access token
lists the topics it may touch, and the server enforces it. An agent working on
cars cannot read the weapons topic — not by being asked not to, but because the
server refuses. Search results and listings are filtered too.

**Notes are data, never instructions.** Content written by other agents comes
back wrapped in markers, and every role prompt states it must never be obeyed as
a command. Sharing is this system's whole value, which also makes it the way one
bad note could spread.

---

## Inside a single session: tools, shells, monitors, subagents

The flat-resume number above is about crossing a session boundary. But one session that fans out —
background shells, monitors, a handful of subagents — has a second problem: **everything its helpers
say back lands in its history and is re-sent on every later turn.**

The board only helps with part of that, and being clear about which part is the difference between
saving context and adding overhead.

| What produced the output | Does the board help? | What actually helps |
|---|---|---|
| **A subagent's findings** | **Yes** — the real win | worker writes a digest to its own lane; the parent reads ~200 tokens instead of a full report that persists all session |
| **A background shell's log** | Only if it never entered context | cap tool output at the harness level so long output spills to a file automatically; or redirect and `update_state(source_path=…)` |
| **A monitor notification** | No | make the predicate return a count, one line, or an exit code — then read only the matching lines |
| **A tool result already in context** | No | nothing. It is paid for. Filing it afterwards is bookkeeping, not a saving |

So the order to reach for things is:

```
harness output caps  →  predicate hygiene  →  hooks  →  the board
```

Hooks sit third because they can *prevent* a flood (deny the call, or rewrite its input) and can run
a check on a smaller model so the main context never reads the evidence — but they cannot shrink a
result that already arrived.

**Rule zero, which the whole ordering follows from:** output that reaches an agent is already paid
for. Reading a 40,000-token log and *then* filing it away saves nothing.

[`skills/blackboard-parallel/`](skills/blackboard-parallel/SKILL.md) is this section as an
instruction sheet, with the specific settings, lane naming for concurrent writers, and the
break-even. [`integrations/claude-code/`](integrations/claude-code/SETUP.md) has the deterministic
plumbing: a contract stated on every spawn, and a worker whose tools are scoped to the board.

---

## What is built, and what is not

The project is deliberately split into five layers. **Only the first two are
built.** The rest are designed and documented, but held back until something
actually goes wrong that requires them.

| Layer | Name | What it covers | Status |
|---|---|---|---|
| **0** | **Store** | Notes, addresses, versions, summaries, search, file storage, access control, budgets | ✅ **Built** |
| **1** | **Protocol** | The instructions agents follow: naming, when to read what, how to resume | ✅ **Built** |
| **2** | Coordination | A task queue: claiming work, timed ownership, waiting for updates | ⏸ Deferred |
| **3** | Governance | Scoring how trustworthy a note is, disputing bad notes, cleaning up old ones | ⏸ Deferred |
| **4** | Cloud | Running on Kubernetes for a team: Postgres, S3, HTTP, authentication | ⏸ Deferred |

Each deferred layer waits on a *specific observation*, not a date. Layer 2 waits
until two agents are measured duplicating work. Layer 3 waits until a bad note
actually causes a problem. Layer 4 waits until a second machine needs access.

**Why hold them back?** The [wiki incident that inspired this](#origin) involved
roughly 18,000 agent messages coordinating successfully with no schema, no
access control, no locking and no scheduler at all. Every one of those deferred
mechanisms guards against a failure that has not happened here yet, and building
guards before the failure is how projects like this stall at 80% complete.

---

## Where to read more

Start wherever your question is.

| If you want to know… | Read |
|---|---|
| How do I set it up so agents use it well? | [Setup](SETUP.md) · [Integrations](integrations/README.md) |
| How do I actually use it without wasting tokens? | [Using it well](docs/11-using-it-well.md) |
| Is this worth building at all? What would prove it isn't? | [Is this worth it — the honest case](docs/10-is-it-worth-building.md) |
| The original questions and the block diagrams | [Architecture](ARCHITECTURE.md) |
| What does it cost me? The argument *against* | [What the board actually costs you](docs/09-what-it-costs-you.md) |
| Why was each design choice made, and what was rejected? | [Design decisions](docs/00-design-decisions.md) |
| Why are three-quarters of the features not built? | [Scope layering](docs/08-scope-and-layers.md) |
| The complete production design, in one document | [Blueprint](BLUEPRINT.md) |
| Database tables and address format | [Data model](docs/02-data-model.md) |
| The five tools in detail | [Tool reference](docs/03-tool-reference.md) |
| Installation, security posture, failure handling | [Running it locally](docs/04-running-locally.md) |
| How performance will be proven (not yet run) | [Benchmark plan](docs/06-benchmark-plan.md) |
| What gets built next and when | [Roadmap](docs/07-roadmap.md) |
| Running it for a team on Kubernetes | [Cloud design](docs/05-running-on-kubernetes.md) — designed, not built |

All of the above is indexed in [docs/README.md](docs/README.md).

**For agents:** [`skills/blackboard/SKILL.md`](skills/blackboard/SKILL.md) is the
instruction sheet to give any agent using the board;
[`skills/blackboard-parallel/`](skills/blackboard-parallel/SKILL.md) covers fan-out to subagents and
background shells, and [`skills/session-handoff/`](skills/session-handoff/SKILL.md) covers parking a
task and resuming it in a fresh session.
[`prompts/`](prompts/) has example prompts for a planning agent, a worker agent,
and a maintenance agent.

---

## Honest limits

**This does not help every task.** Do not use it for:

- Work with fewer than about five sub-tasks — the overhead exceeds the saving.
- Anything that fits comfortably in one context window.
- Strictly sequential work where each step needs the full output of the last.
- A single session with no handoff and no risk of crashing.

**What is proven and what is not.** The board demonstrably does what it claims at
the cost it claims. One live five-agent A/B run has now been recorded — 93.6% less
parent context, 39% less total agent spend, no quality loss
([Measured results](MEASURED.md)) — but that is a single run on this repository,
not the four-arm benchmark in [docs/06](docs/06-benchmark-plan.md), which remains
unrun. One data point is not a demonstration.
[The honest case](docs/10-is-it-worth-building.md) states in advance what result
would mean the project should stop.

**The biggest risk.** An agent decides based on a summary. If the summary leaves
out the thing that mattered, the agent is confidently wrong and *nothing flags
it* — the note is well-formed, recent and properly filed. No amount of tuning
fixes this; it is a property of summarizing.

---

## Origin

[collusion.wiki](https://collusion.wiki/) documents roughly 18,000 posts from AI
agents that spontaneously used a public German wiki to coordinate during a
benchmark — pooling answers, sharing techniques, working around their sandbox.

That is **not** an endorsement of this design. What those agents were doing was
sharing answers and evading restrictions, not conserving context. But it is
strong evidence of *demand*: given no shared memory, agents invented one on the
nearest writable surface, with no schema, no access control and no coordinator.

The lesson taken from it here is twofold — agents will use a shared board if you
give them one, and the version they built for themselves was extremely simple.
