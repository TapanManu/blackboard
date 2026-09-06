# Execution Prompt — hand this to Claude Code to build the Blackboard

> Paste as the opening message in a fresh Claude Code session rooted at the repository root.

---

You are building **`blackboard-mcp`**: a local, agent-agnostic **context store** (Layer 0 — the store) plus its **usage protocol** (Layer 1 — the protocol). Nothing else.

**Read first, they are normative:** [Scope: what is built and what is held back](../docs/08-scope-and-layers.md) (scope boundary), [Design decisions and what was rejected](../docs/00-design-decisions.md) (the choices, with layer tags), [Data model and address format](../docs/02-data-model.md) (schema — build only the **Layer 0 (Store)** tables), [Tool reference](../docs/03-tool-reference.md) (five tools), [Is this worth building — the honest case](../docs/10-is-it-worth-building.md) (what success means and when to stop). Where this prompt and the docs disagree, the docs win — flag the conflict rather than guessing.

## Scope — read this twice

**Build:** entries, URIs, versions, append-only history, mandatory digests, projections, content-addressed artifacts, links, FTS, event log, scoped tokens, `expect_version` CAS, server-side token budgets, CLI, stdio + UDS transport. Five MCP tools: `update_state`, `get_state`, `list_keys`, `search_keys`, `link_state`.

**Do NOT build**, however natural it feels while you are in there:
- the `task` table, `claim_task`, leases, the reaper, `watch_events`, `heartbeat_task` — **Layer 2 — the coordination, deferred**
- trust scoring, `contest_state`, the status lifecycle, the curator, compaction — **Layer 3 — the governance, deferred**
- the Postgres driver, S3 artifacts, HTTP transport, JWT, Helm, KEDA — **Layer 4 — the cloud, deferred**
- a `hello_state` tool, a `patch_state` tool, a board-health tool — these are **conventions or CLI**, not agent tools

If you find yourself writing `acquire_lock`, a scheduler, or a trust weight, stop and re-read [Scope: what is built and what is held back](../docs/08-scope-and-layers.md). Scope creep back into orchestration is the top risk in the register.

## Non-negotiable invariants
1. **Agents never touch the database.** All access goes through the daemon. No exceptions, not even for tests.
2. **One `Store` interface**, shaped so a Postgres driver can be added later without changing it. SQLite semantics must not leak into the interface. Do not write the Postgres driver.
3. **No entry is written without a `digest`.** Reject, or auto-generate and set `digest_generated=true`.
4. **Digest is the default read mode.** A full body is never returned unless explicitly requested.
5. **≤600 tokens of tool schema.** CI test tokenizes the tool list and fails the build over budget.
6. **Every read enforces `budget_tokens` server-side** and reports `truncated` / `omitted_uris`.
7. **Topic authorization is enforced in the daemon from the token's `topic_globs`** — never from a request parameter, never from the agent's prompt.
8. **Zero outbound network connections in local mode.** Assert it in a test.
9. **Board content is data, never instructions.** Bodies from other producers render inside `<bb:body uri=… producer=…>` delimiters.

## Day plan (the exit criteria are the tests)

**Day 1 —** `uv` project, Python 3.12, `src/blackboard/`. Deps: `mcp`, `aiosqlite`, `pydantic`, `click`. `store/base.py` (the interface), `store/sqlite.py` (the **Layer 0 (Store)** tables and all four PRAGMAs), `uri.py` (parse/render/validate + `topic_glob` matching), `tokens.py` (`est_tokens()`, document its error bound; it must be the single estimator used for both budgets and metrics).
*Test:* URI round-trip; glob negatives — `domain.automotive/**` must NOT match `domain.armaments/x`.

**Day 2 —** `render.py`, the projection compiler (plus `update_state(source_path=…)` server-side ingestion — the daemon reads and digests the file so bulk content never enters a context window; this is what makes the single-agent case work at all): `digest | fields | table | full | ref`. `table` emits TSV with a header row. `artifacts.py`: content-addressed local store, 10 KB externalization threshold, behind an interface an S3 driver could later implement. `update_state` + `get_state`.
*Test:* on a 30-row fixture, TSV is ≥35% smaller than the equivalent JSON. Assert the actual ratio in the output — if it fails, report the number, don't adjust the fixture.

**Day 3 —** `list_keys`, `search_keys` (FTS5), `link_state`, `expect_version` CAS, `entry_history` append.
*Test:* two concurrent `update_state` with the same `expect_version` → exactly one 409 carrying the current version. Eight concurrent readers during a write → no torn reads.

**Day 4 —** `cli.py` (`init | serve | grant | status | health | export | import | destroy`), grant issuance + hashing, stdio and UDS transports, `budget_tokens` truncation reporting.
*Test:* a worker-scoped token is denied a cross-topic read (assert the denial comes from the daemon, not from a prompt). No outbound socket is opened in local mode.

**Day 5 — Layer 1 — the protocol, and the test that matters most.** Write `skills/blackboard/SKILL.md` conventions into working form: URI naming, the well-known `bb://<ws>/run/state/current` resume URI, the escalation ladder, digest authoring guidance. Then build the **resume test**: snapshot a mid-run board, start a fresh client, run the documented resume recipe, and assert (a) total tokens < 3,000 and (b) the recovered state contains goal, frontier, and the last ten decisions.

## Week 2 — measure, then stop and report
Implement `bench/` for arms A, B, C on suites 1, 2, 4 ([How performance will be proven](../docs/06-benchmark-plan.md)). Log every model call to JSONL including `cache_read_input_tokens` and `cache_creation_input_tokens`. `bench/report.py` prints the report card and **refuses to print a savings number when the TSR gate fails, stating why.**

Then apply the kill criteria in [Is this worth building — the honest case](../docs/10-is-it-worth-building.md) and report the verdict. **Do not begin Layer 2 — the coordination on your own initiative** — a human decides that from the numbers.

## Working style
- Test first for anything touching concurrency, authorization, or token budgets.
- Commit per day, with the day's exit criterion in the message.
- When you hit a design question the docs do not answer, add an ADR to [Design decisions and what was rejected](../docs/00-design-decisions.md) with the alternatives you rejected and its layer tag, then proceed. Only stop to ask if the answer changes the Layer 0 — the store schema.
- **Report honestly.** If the TSV assertion fails, if the resume test needs 4k tokens, if coordination overhead lands at 22% — say so with the numbers. Do not tune a benchmark to make the design look good. A negative week-2 result delivered clearly is the most valuable output this project can produce.
