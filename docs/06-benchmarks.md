# Benchmark Suite — PoV Report Card

> **This runs in week 2, against L0 + L1 only** (`docs/07-roadmap.md`). Its output feeds the kill criteria in `docs/09-value.md`. Nothing in L2–L4 is built before this report exists.

## Protocol
- **Arms:**
  - **A — Baseline:** single Opus session, no blackboard, natural sub-agent spawning allowed.
  - **B — Ecosystem, no board:** Opus planner + Haiku workers, prompt-copy handoff. *Isolates how much of the win is the board vs. just cheaper models.* Do not skip this arm; without it a reviewer will assume the savings are model substitution.
  - **C — Ecosystem + Blackboard:** Opus planner + Haiku workers + `bbd`.
  - **D — Single Opus + Blackboard:** answers Q8 empirically.
In L0 there is no scheduler: in arms B and C the planner writes `kind=task_spec` entries and worker sessions are started against them. Arm C differs from B only in that inputs are passed as URIs and results come back as digests — which is exactly the effect being measured.

- **n = 5** paired runs per arm per task. Report **median + IQR**, not mean. Fixed temperature, fixed task inputs, randomized arm order.
- **Gate:** report savings only where `TSR_C ≥ TSR_A − 2pp`. A cheaper wrong answer is not a result (D15).

## Task suites
1. **Multi-repo audit** (parallel-friendly): analyze 12 modules for a defect class, produce a consolidated report. Deterministic ground truth: seeded defects.
2. **Long-horizon build** (sequential, memory-heavy): 30+ step feature implementation. Tests resumption and decision retention.
3. **Research synthesis** (fan-out/fan-in): 8 sources → structured comparison. Tests digest fidelity.
4. **Interrupted run** (resilience): kill the session at step 60%; a fresh agent resumes. Measures Recovery Time and post-resume TSR.

## Metrics
| Metric | Formula | Target |
|---|---|---|
| TRR — Token Reduction | `1 − Σtok_C / Σtok_A` | ≥ 0.50 |
| CRR — **Cost** Reduction | `1 − $_C / $_A` | ≥ 0.70 (model-mix effect) |
| TTS — Time to Solution | wall clock, first prompt → accepted answer | ≤ 0.4 × A |
| PEI — Parallel Efficiency | `T_serial / (T_parallel × workers)` | 0.5–0.7 realistic |
| **TSR — Task Success** | rubric (0–1) + deterministic checks | **≥ A − 2pp (gate)** |
| Peak Context | max window occupancy per agent | ≤ 25% of A |
| CHR — Cache Hit Rate | `cache_read_input / total_input` | ≥ 0.6 planner |
| Rework Rate | retries / tasks | ≤ 0.15 |
| Coordination Overhead | board-I/O tokens / total tokens | ≤ 0.15 |
| Recovery Time | tokens & seconds cold-start → operational | ≤ 3k tok, ≤ 10 s |
| Board Health | see below | ≥ 0.85 |

```
Board Health = 0.30·schema_valid_frac + 0.25·(1 − contested_frac)
             + 0.20·mean_trust + 0.15·(1 − dangling_ref_frac)
             + 0.10·(1 − expired_lease_frac)
```

## Instrumentation
Every model call is logged to `bench/runs/<run_id>.jsonl`:
```json
{"ts":..., "run":"c-audit-03", "arm":"C", "agent":"worker-2", "model":"claude-haiku-4-5-20251001",
 "input_tokens":1840, "cache_read_input_tokens":1200, "cache_creation_input_tokens":0,
 "output_tokens":410, "latency_ms":2310, "task_id":"t7", "phase":"execute"}
```
Cost is computed from a per-model price table, not assumed. `bench/report.py` emits the table below plus a Grafana-ready CSV.

## Report card template
| Metric | A: Opus solo | B: Ecosystem, no board | C: Ecosystem + BB | D: Opus + BB |
|---|---|---|---|---|
| Total tokens | | | | |
| Cost (USD) | | | | |
| TTS (s) | | | | |
| TSR | | | | |
| Peak context | | | | |
| Cache hit rate | | | | |
| Rework rate | | | | |
| Recovery time | n/a | n/a | | |

## Kill criteria (from `docs/09-value.md`)
| Signal | Fail threshold |
|---|---|
| Coordination overhead | > 15% |
| TSR vs. baseline | worse by > 2pp |
| Digest → full escalation rate | > 30% |
| Resume test | fails, or > 3k tokens |
| Tokens saved vs **arm B** | < 25% |

Two of five failing = stop. Decide this now, while it is cheap to be objective.

## Expected shape of results (hypotheses to falsify, not claims)
- **C beats A on cost by 5–10×**, driven mostly by model mix (visible as B ≈ C on cost) and by eliminating the `O(T²)` re-read (visible as C ≪ B on tokens). Separating these two effects is the entire point of arm B.
- **C beats B on tokens by 40–60%** — the board's specific contribution.
- **TTS improves 2–4×** on parallel-friendly suites; roughly **no improvement** on suite 2 (sequential), which is the honest limit of the approach and should be reported as such.
- **D (single agent + board)** shows modest token savings but a large **Peak Context** and **Recovery Time** win — the real Q8 answer.
- **Suite 4** is where the board wins outright: A cannot resume at all.

Publishing a result where the ecosystem loses on a suite is more credible than four green rows. Report suite 2 even if flat.

**No invented numbers.** The original draft of this project carried "~88% token savings, 4.7× speedup" with no run behind them. Ship measured numbers or ship none.
