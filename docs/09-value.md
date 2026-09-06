# Does this project have value? — the honest case

## The claim I will defend

> A local, addressable, digest-first shared store lets agent work survive session death and lets multiple agents avoid recomputing each other's results — at a coordination overhead low enough to be worth it on tasks above roughly five subtasks.

That is narrower than the original framing. It is also defensible, measurable in a week, and not provided by anything else in the stack today.

## Three sources of value, ranked by confidence

**1. Session resumption — high confidence, unique.**
Today a context limit, a crash, or a `/clear` destroys work. Nothing else recovers it. The resume path is ~2k tokens to full operational standing regardless of how much work preceded it: goal, constraints, frontier, and the last ten decisions. The decisions matter most — that is what a fresh agent otherwise re-litigates from scratch.

This alone justifies L0. It requires no second agent, no orchestration, and no trust machinery.

**2. Cross-agent memoization — high confidence, directly evidenced.**
This is what actually produced the win in the collusion.wiki case: don't recompute what another agent already computed. Two sessions resolving the same dependency, two agents analyzing the same module, a runbook re-derived weekly. `put` + `get` + `search` is the entire mechanism.

**3. Context-cost linearization — medium confidence, must be measured.**
The `O(T²) → O(T·k·d)` argument is sound in principle, but the overhead in `docs/08-costs.md` is real and paid up front: tool schemas every turn, digest generation in expensive output tokens, round-trip framing, orientation tax. Whether the trade nets out is an empirical question, not an architectural one. Do not claim it before arm B and arm C are run.

## Claims I am dropping

- **"O(1)."** It is O(1) *per step*. Overstating this loses a technical audience in one sentence.
- **"~88% token savings, 4.7× speedup."** Those numbers in the original draft were invented. Ship measured numbers or none.
- **"Validated by the OpenAI agent wiki."** That was benchmark leakage and sandbox evasion, not context optimization. It is evidence of *demand* — agents built a blackboard when none was offered — not endorsement of this design.
- **Trust scores as a headline feature.** A heuristic wearing a number. Useful later; not a selling point now.

## Kill criteria — decide against these, not against enthusiasm

Run L0 + L1 for one week, then check:

| Signal | Threshold | If it fails |
|---|---|---|
| Coordination overhead (board I/O ÷ total tokens) | > 15% | The board is not paying for itself. Stop. |
| Task Success Rate vs. solo baseline | worse by > 2pp | Digest lossiness is destroying quality. Stop or redesign the digest rule. |
| Digest escalation rate (`digest` → `full`) | > 30% | The escalation ladder is costing more than reading full directly. Redesign digests. |
| Resume test | fails, or > 3k tokens | The one unambiguous win doesn't work. Stop. |
| Tokens saved on a real multi-agent task | < 25% vs. arm B | The board adds nothing over cheap prompt-copy fan-out. Stop. |

Two of these five failing means the honest answer is no. Write that down now, while it is cheap to be objective.

## Where it is net-negative — do not use it

Fewer than ~5 subtasks. Work that fits in one context window. Strongly sequential work where each step needs the full previous output. Exploratory work you cannot decompose yet. Single session with no handoff and no crash risk. Irreducible context — one large file read end to end.

Publishing this list makes the positive claims credible. A tool that claims to help everywhere helps nowhere.

## Verdict

**Yes, with a narrowed claim and a one-week proof.** Resumption and memoization are real, unmet, and cheap to build. Context linearization is plausible and testable. The original six-week design was mitigating failures nobody has observed; L0 + L1 tests the thesis in a week for roughly a tenth of the effort.

If the week's numbers land, everything in L2–L4 remains available and unblocked. If they don't, you spent a week instead of six.
