# Roadmap — evidence-gated

Rewritten after the collusion.wiki review. The old plan was six phases before any measurement. This one measures in week one.

## Week 1 — L0 + L1 (the whole bet)

| Day | Work | Done when |
|---|---|---|
| 1 | `uv` project; SQLite schema (L0 tables only); URI parse/render/glob; token estimator | Glob negative cases pass (`domain.automotive/**` must not match `domain.armaments/x`) |
| 2 | `update_state` / `get_state` with digest-first + `budget_tokens` truncation; artifact externalization at 10 KB | TSV fixture is ≥35% smaller than equivalent JSON |
| 3 | `list_keys` + `search_keys` (FTS5) + `link_state`; `expect_version` CAS | Two concurrent puts with the same `expect_version` → exactly one 409 |
| 4 | CLI (`init/serve/grant/status/export/import/destroy`); scoped tokens; stdio + UDS transport | Cross-topic read is denied by token, not by prompt; no outbound network connection in local mode (asserted by test) |
| 5 | L1: skill prompt, URI conventions, resume recipe, reference role prompts; the resume test | Fresh session reaches operational standing in **< 3k tokens** from a mid-run board snapshot |

## Week 2 — measure, then decide

Run arms A (Opus solo), B (ecosystem, prompt-copy, no board), and C (ecosystem + board) on suites 1, 2, and 4 from `docs/06-benchmarks.md`. n=5.

**Then apply the kill criteria in `docs/09-value.md`.** Two of five failing = the honest answer is no.

## Only if week 2 justifies it

| Layer | Trigger — an observation, not a plan | Effort |
|---|---|---|
| **L2 Coordination** — tasks, claim, lease, watch | Two agents measurably duplicated work, and self-organization via `task_spec` entries was insufficient | 3–4 d |
| **L3 Governance** — trust, contest, lifecycle, curator | Corruption or confidently-wrong entries **measured** in a real run; or a workspace crossed ~5k entries | 1 w |
| **L4 Cloud** — Postgres, S3, HTTP, JWT, Helm, KEDA | A second machine actually needs the board | 1 w |

Each trigger is an event you observe, not a milestone you schedule. Promotion from convention to code is one-way and evidence-gated.

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Digest omits what mattered; planner confidently wrong | **High** | Escalation to `mode=full` always available; track escalation rate; this is the top kill criterion |
| Coordination overhead exceeds savings on real tasks | **High** | It is measured in week 2 and it is a kill criterion |
| Prompt injection via board content | Medium | Board content is data, not instructions; render untrusted bodies in explicit delimiters; stated in the skill |
| Deletion / retention obligations | Medium | Decide before L0 ships whether regulated data may touch the board; append-only history makes redaction hard |
| Agents ignore conventions and dump prose | Medium | Server rejects a missing digest; conventions that fail get promoted to enforcement |
| Scope creep back into orchestration | **High** | `docs/08-layers.md` names the boundary. Any `claim`/`lease`/scheduler work is L2 and needs a trigger. |
| Building L2–L4 before week 2 concludes | High | Explicitly forbidden in `prompts/BUILD_PROMPT.md` |
