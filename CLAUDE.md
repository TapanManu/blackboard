# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this project is

A local context store for AI agents. Agents write notes with mandatory short
summaries; other agents — including ones in later sessions — read the summaries
cheaply instead of re-reading everything. See [the README](README.md).

Layer 0 (the store) and Layer 1 (the protocol agents follow) are built and
tested. Layers 2–4 are designed but deliberately not built; each waits on a
specific observed failure, not a date. Do not build them without that trigger —
see [Scope: what is built and what is held back](docs/08-scope-and-layers.md).

## Running things

```bash
uv run pytest -q                              # 120 tests, ~3s
uv run blackboard-mcp -w <workspace> init
uv run blackboard-mcp -w <workspace> grant --role planner --quiet
```

Tests requiring the exact tokenizer or the MCP transport skip automatically if
those optional packages are absent. Install everything with
`uv pip install -e '.[dev,mcp]'`.

---

# CRITICAL: Documentation standard

**Every Markdown file in this repository exists to transfer information to a
human who has never seen this project before.** Not to record that a decision
happened. Not to look thorough. To be *understood*, on the first read, by someone
who arrived from a search result.

This applies to [the README](README.md), [architecture and diagrams](ARCHITECTURE.md), everything in `docs/`, and every
commit message and pull request description. If a reader has to scroll back,
guess, or open a second file to parse a sentence, that sentence has failed.

## The rules

**1. Never use an abbreviation you have not defined on that page.**
Not `L0`, `TRR`, `PEI`, `WAL`, `FTS`, `CAS`, `validity score`, `KV`, `Δ3`, `TTS`.
Define it at first use, or use plain words instead. A term defined in another
file is undefined for this reader.

> ✗ `L0 store (entries, URIs, digests, projections, FTS, CAS, scoped tokens)`
> ✓ `Layer 0, the store: notes, addresses, versions, summaries, search, access control`

**2. Link text says what the reader will find, never the filename.**
A filename is an implementation detail. [Is this worth building — the honest case](docs/10-is-it-worth-building.md) tells a newcomer
nothing; the same link labelled by its content tells them whether to click.

> ✗ `The reasoning is in [Is this worth building — the honest case](docs/10-is-it-worth-building.md) — read that first.`
> ✓ `[Is this worth building — the honest case](docs/10-is-it-worth-building.md)`

**3. Give every code-named thing a plain-language name, and lead with that.**
Internal shorthand is fine *after* the reader knows what it refers to.

> ✗ `L2 is deferred pending trigger.`
> ✓ `Layer 2 — the task queue — is not built yet. It waits until we actually see two agents duplicating work.`

**4. Lead with what it does, not what it is made of.**
Open every document and every section with the reader's question, not the
implementation.

> ✗ `A local, agent-agnostic context store using SQLite-backed key-value storage with JSON schema validation and MCP bindings.`
> ✓ `A shared notepad for AI agents. It runs on your machine and lets a new agent pick up where a previous one stopped.`

**5. Show the problem concretely before the solution.**
Numbers, or a small worked example. "Reduces token consumption" is a claim;
"step 5 re-reads 8,000 words, step 50 re-reads 200,000" is information.

**6. Every number is either measured or labelled as a target.**
Never publish an invented figure. If a test produced it, say which. If it is a
goal, write "target". This repository lost its original benchmark table for
exactly this reason — see [measured results](MEASURED.md).

**7. State the limits in the document that makes the claim.**
Where it does not work, what is unproven, what would falsify it. A page that only
sells is not documentation. Put the limits *in* the README, not in a file the
enthusiastic reader will never open.

**8. Order sections by what a newcomer asks first.**
What is it → why should I care → does it work → how do I try it → how does it
work → what are the limits → where do I read more. Not: scope, then plan, then
status.

**9. Explain notation on first use.**
`O(N²)` is not common knowledge. One line — "twice the work costs four times as
much" — costs nothing and loses no one.

**10. Tables for anything with more than two parallel items.**
Prose lists of five things with attributes are unreadable. Give them columns.

## Before you commit a Markdown change

Read it as someone who has never seen this repository:

- [ ] Could I read this page top to bottom without opening another file?
- [ ] Is every abbreviation defined on this page, before it is used?
- [ ] Does every link tell me what I will find, rather than a filename?
- [ ] Does it open with what this is *for*, not what it is *built from*?
- [ ] Is every number either measured-and-cited or explicitly a target?
- [ ] Are the limits stated here, not deferred to a page nobody opens?

If any answer is no, it is not ready.

## Known debt

[the README](README.md) and [architecture and diagrams](ARCHITECTURE.md) follow this standard. **The files in `docs/`
do not yet** — they still use layer numbers, change markers (`Δn`), metric
abbreviations, and filename link text. They were written as working design notes
before this standard existed. Bring each one up to standard when you next touch
it; do not add new jargon in the meantime.

---

## Code conventions

- **Stdlib only in the core.** `tiktoken` is needed only for benchmarks, `mcp`
  only for the agent transport. Keep installation to one command.
- **Agents never touch the database.** Everything goes through the API layer in
  `src/blackboard/api.py`.
- **Write the test first** for anything touching concurrency, access control, or
  token budgets. Every bug found so far came from a test written before the fix.
- **Never widen a failing assertion to make it pass.** The tool-schema budget test
  and the tokenizer-accuracy test exist to fail. When they do, fix the code or
  correct the documented claim — the token estimator was found to be 106% wrong
  precisely because its test compared it against a real tokenizer.
- **Report measurements honestly**, including unfavourable ones. A benchmark tuned
  to flatter the design is worse than no benchmark.
