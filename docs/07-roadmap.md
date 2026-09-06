# Roadmap and what triggers each layer

**For:** anyone asking what happens next. Nothing later is scheduled by date — each remaining layer waits on a specific thing going wrong first.

Rewritten after the collusion.wiki review. The old plan was six phases before any measurement. This one measures in week one.


## Terms used on this page

*(Project-wide vocabulary — entry, digest, workspace, topic — is in the [README](../README.md#vocabulary).)*

| Term | Meaning |
|---|---|
| **CAS (compare-and-swap)** | Write only if the entry is still at the version you last read; otherwise the write is rejected. Replaces locking. |
| **FTS5** | Version 5 of SQLite's full-text search extension. |
| **UDS (Unix domain socket)** | A local-only connection between processes on one machine. Not built; stdio is used instead. |
| **KEDA** | A Kubernetes add-on that starts and stops workers based on a metric — here, how many tasks are waiting. |
| **TSV (tab-separated values)** | Rows of data with one header line — far cheaper in tokens than JSON for repetitive records. |

## Week 1 — Layers 0 and 1 (the whole bet)

| Day | Work | Done when |
|---|---|---|
| 1 | `uv` project; SQLite schema (Layer 0 — the store tables only); URI parse/render/glob; token estimator | Glob negative cases pass (`domain.automotive/**` must not match `domain.armaments/x`) |
| 2 | `update_state` / `get_state` with digest-first + `budget_tokens` truncation; artifact externalization at 10 KB | TSV fixture is ≥35% smaller than equivalent JSON |
| 3 | `list_keys` + `search_keys` (FTS5) + `link_state`; `expect_version` CAS | Two concurrent puts with the same `expect_version` → exactly one 409 |
| 4 | CLI (`init/serve/grant/status/export/import/destroy`); scoped tokens; stdio + UDS transport | Cross-topic read is denied by token, not by prompt; no outbound network connection in local mode (asserted by test) |
| 5 | Layer 1 — the protocol: skill prompt, URI conventions, resume recipe, reference role prompts; the resume test | Fresh session reaches operational standing in **< 3k tokens** from a mid-run board snapshot |

## Week 2 — measure, then decide

Run arms A (Opus solo), B (ecosystem, prompt-copy, no board), and C (ecosystem + board) on suites 1, 2, and 4 from [How performance will be proven](06-benchmark-plan.md). n=5.

**Then apply the stop criteria in [Is this worth building — the honest case](10-is-it-worth-building.md).** Two of five failing = the honest answer is no.

## Only if week 2 justifies it

| Layer | Trigger — an observation, not a plan | Effort |
|---|---|---|
| **Layer 2 — the coordination Coordination** — tasks, claim, lease, watch | Two agents measurably duplicated work, and self-organization via `task_spec` entries was insufficient | 3–4 d |
| **Layer 3 — the governance Governance** — trust, contest, lifecycle, curator | Corruption or confidently-wrong entries **measured** in a real run; or a workspace crossed ~5k entries | 1 w |
| **Layer 4 — the cloud Cloud** — Postgres, S3, HTTP, JWT, Helm, KEDA | A second machine actually needs the board | 1 w |

Each trigger is an event you observe, not a milestone you schedule. Promotion from convention to code is one-way and held until evidence justifies them.

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Digest omits what mattered; planner confidently wrong | **High** | Escalation to `mode=full` always available; track escalation rate; this is the top kill criterion |
| Coordination overhead exceeds savings on real tasks | **High** | It is measured in week 2 and it is a kill criterion |
| Prompt injection via board content | Medium | Board content is data, not instructions; render untrusted bodies in explicit delimiters; stated in the skill |
| Deletion / retention obligations | Medium | Decide before Layer 0 — the store ships whether regulated data may touch the board; append-only history makes redaction hard |
| Agents ignore conventions and dump prose | Medium | Server rejects a missing digest; conventions that fail get promoted to enforcement |
| Scope creep back into orchestration | **High** | [Scope: what is built and what is held back](08-scope-and-layers.md) names the boundary. Any `claim`/`lease`/scheduler work is Layer 2 — the coordination and needs a trigger. |
| Building Layers 2 to 4 before week 2 concludes | High | Explicitly forbidden in `prompts/BUILD_PROMPT.md` |
