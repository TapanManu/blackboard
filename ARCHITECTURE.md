# Architecture

This document holds the questions that started the project, the answers the
design settled on, and the diagrams. It assumes you have read the
[README](README.md) but nothing else.

**Contents:** [Terms](#terms-you-will-need) · [The brief](#1-the-original-brief) ·
[The fifteen questions](#2-the-fifteen-questions) ·
[Diagrams](#3-system-architecture) · [Changes from the first draft](#9-changes-from-the-original-draft)

---

## Terms you will need

| Term | Meaning |
|---|---|
| **Token** | The unit an AI model reads and is billed in — roughly ¾ of a word. |
| **Context window** | Everything a model can see at once. The scarce resource this project conserves. |
| **KV cache** | The model's internal working memory for one request. Private to that request; two sessions never share one. |
| **Prompt caching** | A billing optimization: if a request starts with the exact same text as a previous one, the provider reuses its computation and charges less. It matches from the *beginning* of the text, so one changed character early on undoes it. |
| **Entry** | One note on the board. |
| **Digest** | The mandatory short summary attached to every entry (≤200 tokens). |
| **Topic** | A subject area used to keep unrelated work apart, e.g. `domain.automotive`. |
| **MCP** | Model Context Protocol — the standard way an AI agent connects to an external tool. Vendor-neutral. |
| **The board** | This system. |

**Reading the complexity notation.** A few answers use `O(...)`, a standard way to
describe how cost grows:

- `O(1)` — constant. Cost does not change as things get bigger.
- `O(N)` — linear. Twice the work costs twice as much.
- `O(N²)` — quadratic. Twice the work costs *four* times as much. This is the
  shape the project exists to eliminate.

---

## 1. The original brief

> **Blackboard to store context across Agents.** Inspired by
> [collusion.wiki](https://collusion.wiki/).

### What it had to do

1. Reduce token and context use across multiple agents and multiple sessions
2. Be a home for repeated tasks, instructions and runbooks
3. Let two or more agents finish a job faster and cheaper than one agent alone
4. Be simple to install, set up, use quickly, and disconnect
5. Allow tasks to run more often, with latency you can predict from the plan
6. Use a shared communication format that is cheap in tokens
7. Keep every agent's context window light
8. Store everything locally or in a sandbox — never a third-party service
9. Work with any agent or model, while still being aware of the task at hand
10. Stay simple; actively rule out complexity

### The payoff being chased

Use an expensive, capable model to **plan and delegate**; use cheap, fast models
to do the atomic pieces; have the expensive model recombine the results — with the
board as the medium they pass work through. Optionally a separate coordinator
maintains the board itself.

### Problems flagged from the start

1. Which measurements would actually prove any of this?
2. If the board grows without limit, does old unused content need cleaning up —
   and would that cleanup cost more complexity than it saves?

### Explicitly not this project's job

Deciding how many agents run or which model each uses · designing how the agent
team is organized · optimizing the model's internal caches · restricting what may
be written to the board (anything may be) · defining how agents connect to tools.

---

## 2. The fifteen questions

Short answers here; the full reasoning is in
[Questions answered in detail](docs/01-questions-answered.md).

### Q1. Are two Claude or Gemini sessions really separate agents, with their own memory?

**Yes, completely.** Two sessions share the model's weights and nothing else —
separate conversations, separate working memory. Neither can see the other's
context. There is no hidden channel between them.

One wrinkle worth knowing: prompt caching matches on the *opening text* of a
request, not on who sent it. So if two agents begin with byte-identical
instructions, the second one benefits from the first one's cached computation.
That is not shared memory — neither can read the other's data — but it does make a
stable, standard instruction block cheaper for everyone using it.

### Q2. If they are separate, how do they share anything?

Only through something outside both of them. Three options, best first:

1. **A shared store like this one** — durable, addressable, survives a session ending.
2. **Copying context into the next agent's prompt** — simple, but you pay for the
   same text once per agent.
3. **Plain files** — works, but with no versions, no summaries, and no way to stop
   two agents overwriting each other.

### Q3. When an agent spawns helper agents, how do they talk?

**Only through the parent, in one direction at a time.** The parent writes a
prompt for each helper; each helper returns a final report. Helpers never talk to
each other. This makes the parent both a bottleneck and a token multiplier.

### Q4. Is that a hidden token cost?

**Yes — this is the core waste.** Two compounding effects:

- **Going out:** each helper receives a full copy of the background. Four helpers,
  one 40,000-token document, means 160,000 tokens paid.
- **Coming back:** each helper returns prose the parent must read — and then
  re-read on every subsequent turn. The parent's own cost grows as `O(N²)`.

With the board, the document is written once and each helper gets an address
(~200 tokens). Reports come back as `{status, address, summary}` instead of essays.

### Q5. Can a shared board make lookups instant — `O(1)`?

**Per step, yes. Overall, no** — and the difference matters.

Two separate things get confused here. *Database lookup speed* was never the
problem; that was always fast. The real problem is what an agent must **re-read
every turn**. Without a board that grows with the conversation, so a task of `T`
steps costs `O(T²)` in total. With a board, each turn reads a fixed handful of
summaries no matter how much work came before — so the total is `O(T)`, linear.

Say **"constant per step."** Claiming plain `O(1)` overstates it and is the
fastest way to lose a technical reader.

### Q6. Do big context windows actually hurt?

Yes, four ways: **cost** rises linearly and is paid every turn; **latency** rises
because processing scales with length; **accuracy** drops because facts in the
middle of long inputs get overlooked; and **distraction** sets in, because
abandoned approaches from earlier still sit there reading as though they were
true.

The board addresses the last two as much as the first two — superseded work is
simply *not present*, rather than present but out of date.

### Q7. Which storage format is best?

The options considered were: (A) tables/TSV, (B) JSON or BSON, (C) key–value,
(D) graphs, (E) prose or binary.

**Answer: store JSON under key–value addresses, but render it differently
depending on shape, and keep relationships in a separate link table.**

| Option | Verdict |
|---|---|
| **Tables / TSV** | **Adopted for output.** Measured **44.6% fewer tokens** than JSON for 30 similar rows, because column names appear once instead of on every row. Poor fit for nested data. |
| **JSON** | **Adopted for storage.** Models already speak it; it can be validated and queried. |
| **BSON** | **Rejected.** Binary storage blocks database queries and saves no *tokens* — tokens are counted on the text a model reads, not the bytes on disk. |
| **Key–value** | **Adopted as the addressing scheme.** This is the `bb://` address, not a competitor to JSON. |
| **Graphs** | **Adopted in small form.** A simple link table answers "where did this come from" without a graph database. |
| **Prose** | **Rejected as a data format, kept as the summary.** Too vague for values, unbeatable for a 200-token "what is this". |
| **Binary** | **Rejected.** An agent cannot read it without a decoding step, so you pay the tokens anyway plus a round trip. |

### Q8. Does a *single* agent benefit? Does it help the model's cache?

**Yes — but not where it first appears, and one common claim about it is false.**

The false claim: the board cannot remove text an agent has already read. A
conversation only grows. Filing away a 40,000-token result *after* reading it
refunds nothing.

The real benefits all come from **crossing a boundary**:

1. **Surviving the session ending** — the unique one.
2. **Surviving summarization** — when a long session gets compressed, detail is
   lost to whatever rule the tool uses. Board content survives word for word.
3. **Not re-deriving things** — for content already on the board.
4. **Never reading the file at all** — ask the server to ingest a file by path and
   the contents never enter the agent's context.

On caching: the board only helps if board content is kept at the **end** of the
context, never at the start. Caching matches from the beginning, so putting
freshly-read board content near the top would undo the cache on every read and
make the board a net loss.

**The caveat:** attaching the board adds roughly 1,500 tokens to every turn (tool
descriptions plus instructions). For one agent, in one session, with no handoff
and no crash risk, that is pure cost. **A single agent's break-even depends on how
many boundaries the task crosses, not on how big it is.**

### Q9. Is throwing detail away really "lossless compression"?

No, and the distinction is the useful part. **Two different things are compressed
differently:**

- **The conversation** — deliberation, retries, dead ends — is discarded almost
  entirely, on purpose. Keeping it causes the distraction problem in Q6.
- **The facts and decisions** are kept exactly, and stored files are byte-identical
  and hash-verified.

**The risk this creates, stated plainly:** the structure defines what is kept, so
anything it did not anticipate is gone for good. Guarded by a free-text field on
every entry, by keeping original files long enough to re-extract from, and by only
ever adding fields rather than removing them.

### Q10. Can a new agent take over mid-task cheaply? ★ And behave as though it had been there?

**Yes. Measured at 2,679 tokens, and that number does not grow with the project.**

The new agent reads three things: the goal and constraints, the list of what is
done and in flight, and the last ten decisions with their reasoning.

On the starred part — "having been there" turns out to be four things, three of
which are recoverable: the goal, **the decisions already made and why** (the one
that naive resumption always loses, which is why fresh agents re-argue settled
points), and the state of the work. The fourth — an intuitive feel for the
problem — is *not* recoverable by any design. It is compensated for by writing
decisions down explicitly rather than leaving them implicit.

**On the risk of a corrupted board misleading a new agent:** the defenses are
layered, and most of them are Layer 3 — deliberately not built yet.

### Q11. Can the protocol and API calls be made cheaper?

**Yes, five ways.** The biggest is the one people miss: **tool descriptions are
re-sent on every single turn of every agent.** Thirty tools can burn 4,000–6,000
tokens per turn before any work happens. This project keeps five tools totalling
**395 tokens**, enforced by an automated test.

Then: pass addresses instead of contents; enforce a token budget at the server;
batch reads into one call rather than several; return summaries by default. And
keep the tool list **fixed** — a list that changes between sessions defeats
prompt caching for everyone.

### Q12. How do two agents split a question and come back together?

The planner writes the shared background **once** and creates a task note per
piece. Each worker reads only its own slice. Each writes back a result and a
summary. The planner reads the two **summaries** — about 400 tokens — and only
opens a full result if something looks wrong.

Their separate internal caches never mattered; they were never going to be shared.

### Q13. What should be measured?

Token reduction, time to finish, and how well work parallelizes. Plus the ones
that make the numbers believable:

- **Task success rate, as a gate.** A cheaper wrong answer is not a result.
- **Cost in actual currency.** Expensive and cheap models differ roughly 15× in
  price, so a setup can use *more* tokens and still cost far less.
- **Coordination overhead** — tokens spent on board reads and writes as a share of
  the total. Above about 15%, the board is not paying for itself.

### Q14. Is a message queue or broker needed?

**No.** A table of tasks that agents claim one at a time already behaves as a work
queue, and an append-only log of changes already behaves as a notification feed.
Kafka or RabbitMQ would add another service to install and run in exchange for
guarantees this workload does not need. Worth revisiting above roughly 50
simultaneous workers. *(This belongs to Layer 2 — not built.)*

### Q15. How do you keep unrelated subjects separate — say, cars and firearms?

**Three enforced layers:**

1. **Separate addresses** — `bb://project/domain.automotive/...` versus
   `bb://project/domain.armaments/...`.
2. **Access tokens that list permitted subjects** — checked by the server on
   every call. **This is the one that actually holds.** Telling an agent in its
   prompt not to look at something is a request; a token that does not authorize
   it is not.
3. **Different expected shapes per subject** — a car specification cannot be filed
   under firearms.

Working across both is possible, but requires explicit permission for both and
leaves an audit trail.

---

## 3. System architecture

Who talks to what. The middle box is the only component that touches storage.

```
+-----------------------------------------------------------------------------------+
|                        PLANNER AGENT (an expensive, capable model)                |
|            - Breaks the job into pieces and names an address for each             |
|            - Reviews results by reading SUMMARIES, not full contents              |
+------------------------------------------+----------------------------------------+
                                           | writes shared background ONCE
                                           | hands out addresses, never contents
                                           v
+-----------------------------------------------------------------------------------+
|                       THE BOARD  (one local process, one database file)           |
|                                                                                   |
|  +------------------------+  +------------------------+  +---------------------+  |
|  | Tool interface         |  | Version control        |  | Summary + output    |  |
|  | 5 tools / 395 tokens   |  | Rejects a write if     |  | formatting          |  |
|  | enforces token budgets |  | someone else wrote     |  | address | summary   |  |
|  |                        |  | first. No locking.     |  | fields | table |all |  |
|  +------------------------+  +------------------------+  +---------------------+  |
|                                                                                   |
|  +------------------------+  +-----------------------------------------------+    |
|  | Access control         |  | Storage: SQLite + large files kept separately |    |
|  | subjects per token     |  | and addressed by their content hash           |    |
|  +------------------------+  +-----------------------------------------------+    |
+------------------------------------------^----------------------------------------+
                                           | reads ONLY its own slice
                                           | writes a result + a required summary
                                           v
+-----------------------------------------------------------------------------------+
|                      WORKER AGENTS (cheap, fast models)                           |
|      - Their token cannot read another worker's subject area                      |
|      - Read cheaply first: address -> summary -> fields -> table -> everything    |
+-----------------------------------------------------------------------------------+
```

## 4. What is built, and what is held back

```
   +---------------------------------------------------------------+
   |  LAYER 4  CLOUD        Run it for a team: Postgres, S3,        |  HELD BACK
   |                        HTTP, login, Kubernetes                 |  until a second
   |                        (also needs Layer 2 first)              |  machine needs it
   +---------------------------------------------------------------+
   |  LAYER 3  GOVERNANCE   Score how trustworthy a note is,        |  HELD BACK
   |                        dispute bad ones, clean up old ones     |  until a bad note
   |                                                                |  causes a problem
   +---------------------------------------------------------------+
   |  LAYER 2  COORDINATION A task queue: claiming work, timed      |  HELD BACK
   |                        ownership, waiting for updates          |  until agents are
   |                                                                |  seen duplicating
   +===============================================================+
   |  LAYER 1  PROTOCOL     The instructions agents follow:         |  *** BUILT ***
   |                        naming, reading order, how to resume    |
   +---------------------------------------------------------------+
   |  LAYER 0  STORE        Notes, addresses, versions, summaries,  |  *** BUILT ***
   |                        search, file storage, access control,   |
   |                        token budgets                           |
   +---------------------------------------------------------------+
```

Each held-back layer waits on **something observed**, not a date on a calendar.
The agents on collusion.wiki coordinated roughly 18,000 messages with none of
these mechanisms, which is the argument for not building them in advance.

## 5. Where the tokens go

The mechanism, with and without the board. One coordinator, four helpers, one
40,000-token document.

```
WITHOUT A BOARD                          WITH THE BOARD
---------------                          --------------
Coordinator holds a 40k document         Writes it to the board ONCE
   |                                        |
   +-- copies 40k --> Helper A  (40k)       +-- "read <address>, part A"  (200)
   +-- copies 40k --> Helper B  (40k)       +-- "read <address>, part B"  (200)
   +-- copies 40k --> Helper C  (40k)       +-- "read <address>, part C"  (200)
   +-- copies 40k --> Helper D  (40k)       +-- "read <address>, part D"  (200)

   <-- 1.5k of prose x4                     <-- {done, address, summary} x4  (200 each)

   Re-reads the whole history               Reads 4 SUMMARIES (800 tokens)
   every turn  ->  grows as O(N²)          every turn  ->  stays flat

   ~166,000 tokens                          ~41,600 tokens
```

## 6. Taking over a half-finished job

The measured result from the test suite.

```
   Session 1 stops at 60% done
   (it may have used 20,000 tokens or 400,000 -- it makes no difference)
        |
        |  the board holds: the goal, what is done, and the decisions made
        v
   Session 2 starts cold, with no memory, and reads three things:

     1. the goal, constraints and current phase
     2. the task list, as a compact table
     3. the last ten decisions and why they were made
        |
        v
   READY TO WORK after 2,679 tokens -- and that number stays FLAT:

     board holds  10,506 tokens  ->  2,679 to catch up  (25.5%)
     board holds 229,566 tokens  ->  2,679 to catch up  ( 1.2%)
     board holds 886,746 tokens  ->  2,679 to catch up  ( 0.3%)
```

## 7. Keeping subjects apart

```
   This agent's token says: subjects = [cars, car tasks]; may read and write

   read  bb://project/domain.automotive/fact/brake     --> ALLOWED
   read  bb://project/domain.armaments/fact/barrel     --> REFUSED by the server
   list  everything                                    --> firearms entries NOT SHOWN
   search "tungsten"                                   --> firearms matches REMOVED

   The server decides, based on the token. Not the request, and not the agent's
   instructions. A refusal does not reveal whether the entry exists.
```

## 8. How the data is organised

```
   entry -------- address (unique) . version . SUMMARY (required) . contents
     |            content hash . size . who wrote it . sources cited
     |
     +-- history    every previous version; nothing is ever overwritten in place
     +-- links      "came from" / "depends on" / "replaces" / "contradicts" / ...
     +-- log        an append-only record of every change
     +-- tokens     access tokens: which subjects, which permissions
     +-- search     full-text index over summaries and contents

   Address:  bb://project/subject/kind/name[@version]
   Files:    stored under a hash of their contents, so identical files are
             stored once, cannot change underneath a reader, and can be verified
```

## 9. Changes from the original draft

The first version of this design was revised in fifteen places. Each change is
marked in [the blueprint](BLUEPRINT.md) with its reason and how hard it would be
to undo. The three worth defending hardest:

| # | Change | Why |
|---|---|---|
| **1** | Replaced explicit locking with "reject the write if someone else got there first" | An agent that hits a rate limit, runs out of context, or simply skips a step would hold a lock forever and freeze the board. Locking assumes the lock-holder stays alive; AI sessions offer no such guarantee. |
| **2** | Replaced a validity score with a multi-signal trust score | The original scored only whether the data was correctly *shaped*, which is almost always yes. It could not detect a well-formed, confident, wrong answer — the exact failure it was meant to catch. |
| **3** | Deleted the performance numbers | "185,000 → 22,000 tokens, 4.7× faster" had no experiment behind it. [Measured results](MEASURED.md) now contains only figures a test actually produced. |
