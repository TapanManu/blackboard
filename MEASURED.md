# Measured Results — Layers 0 and 1

Numbers below come from the test suite (`pytest -s`), computed with the **exact**
`cl100k_base` tokenizer, not an estimate. Reproduce with:

```bash
uv run --python 3.12 --with pytest --with pytest-timeout --with tiktoken pytest tests/ -q -s
```

| Claim | Where it was asserted | Target | **Measured** |
|---|---|---|---|
| Tool-schema surface (re-sent every turn) | `test_server_budget.py` | ≤600 tok | **395 tok** |
| TSV vs JSON for 30 homogeneous rows | `test_render.py` | ≥35% smaller | **44.6% smaller** (516 vs 932) |
| Cold-resume cost from a mid-run board | `test_resume.py` | <3,000 tok | **2,679 tok** |
| Resume cost flat as history grows | `test_resume.py` | ≤1.35× | **1.00×** (2,679 → 2,679 over 120 added entries) |
| Concurrent CAS: exactly one winner of 8 | `test_concurrency.py` | 1 | **1** (7×409, each carrying the current version) |
| No version lost under 30 concurrent writes | `test_concurrency.py` | 30 in history | **30** |
| Network connections in local mode | `test_local_posture.py` | 0 | **0** |

## The headline: resume cost does not grow with the board

| Board content | Full read | Resume | Resume ÷ full |
|---|---|---|---|
| 10,506 tok | 10,506 | **2,679** | 25.5% |
| 229,566 tok | 229,566 | **2,679** | 1.2% |
| 448,626 tok | 448,626 | **2,679** | 0.6% |
| 667,686 tok | 667,686 | **2,679** | 0.4% |
| 886,746 tok | 886,746 | **2,679** | 0.3% |

This is the empirical form of the Q5 claim, and it is the honest one: **resume cost
is flat, so the saving is a function of how much work the board holds.** The ratio
is a property of the workload, not of the system — a board of tiny entries has
little to save. What the system guarantees is the flat line.

## One live A/B run — not from the test suite

Everything above comes from `pytest`. This section does not: it is a single live
run on 2026-09-07, with real agents doing real analysis, recorded because
[the benchmark plan](docs/06-benchmark-plan.md) had produced nothing yet and a
one-off is better than an assumption. **n=1.** Treat it as a data point, not a
result.

**Task:** five agents, five questions about this repository (docs contradictions,
module load-bearing analysis, test coverage, setup-bundle consistency,
deferred-layer triggers). Identical prompts and identical requested depth in both
arms; only the reporting path differed. Arm A returned prose. Arm B wrote a digest
plus body to `bb://sedai/tasks.<lane>/result/exp1` and replied in three lines.

| | Arm A (no board) | Arm B (board) | Delta |
|---|---|---|---|
| Parent context | 36,766 tok | **2,357 tok** | **-93.6%** |
| — agent replies | 36,766 | 957 | |
| — digest read-back | 0 | 1,400 | |
| Internal agent spend | 607,120 tok | 372,112 tok | -38.7% |
| Wall clock, slowest agent | 483 s | 376 s | -22.2% |

Arm B also kept what it found: 20,895 tokens of full bodies on the board,
addressable for the 1,400 spent reading five digests.

**Quality parity held.** Both arms independently found the same core defects. Arm
B additionally found three Arm A missed: `.mcp.json.example`'s `uvx --from .`
omits the `mcp` extra; `server.py:125` resolves the grant once at process start,
so revoke and TTL are inert for a running server; `vacuum` scopes its live set to
one workspace while artifacts are shared across all of them.

**A prediction this run falsified.** The expectation was that Arm B would cost
*more* internally, since each worker loads ~2,600 tokens of skill and schema
before starting. It cost 39% less — composing a 9,500-token prose report is more
expensive than writing a digest plus a body, and the write cost dominates the load
cost.

**What this does not establish.** One run, one repo, one task shape. No
repetition, so run-to-run variance is unmeasured. Both arms used the same model,
so this isolates the reporting path and nothing else. Arm A's prose is richer per
finding than Arm B's digest — the honest claim is that the digests answered the
same questions *at decision level*, with detail retrievable at 3,000-6,000 tokens
per entry. The four-arm design in `docs/06` (n=5 paired, Task Success Rate as a
gate) remains unrun.

## Corrections forced by measurement

**The token estimator was wrong by up to +106%, not the ±15% originally documented.**
Caught by validating against `tiktoken`. A heuristic that over-counts by 2× would
have truncated every read at half its real budget and inflated every benchmark
number. Rebuilt on BPE-style pretokenization and refitted: **max +26.2%, mean
11.6%, biased high** (the safe direction — budgets under-fill rather than
overflow). `tokens.require_exact()` now refuses to let a benchmark report savings
computed from the heuristic.

**The tool surface was 1,036 estimated tokens on first write** — over the 600
budget. The CI test caught it; prose was moved out of the JSON Schema and into the
Layer 1 — the protocol skill prompt, which is loaded once per session instead of re-sent every turn.
Real measurement afterwards: 395.

## Bugs the tests found before any agent did

| Bug | Found by | Fix |
|---|---|---|
| Concurrent writers of identical content raced on one `.tmp` path and renamed a vanished file | `test_concurrent_identical_artifact_writes_converge` | per-writer unique temp name |
| `export` → `import` into a different workspace was rejected, making a "portable dump" unportable | `test_cli.py` | rebase the workspace segment on import; `--keep-workspace` for exact restore |
| `topic/**` did not match the bare topic itself | `test_uri.py` glob table | `/**` compiles to `(?:/.*)?` |

## What a write costs, by shape

`bench/write_shapes.py` holds one payload constant and varies only how it is
written, counting arguments out plus result back with cl100k_base. Four writes
that previously cost 2,435 tokens cost 1,010 — **59% less** — with the largest
single win being `append` instead of reading an entry back to re-emit it (94%).
The table is [`bench/RESULTS.md`](bench/RESULTS.md); the script regenerates it and
refuses to run on the heuristic tokenizer.

Unlike the A/B run below, this one reproduces: one command, committed payload, no
live agents. It measures **unit cost per write**, not whether a real multi-agent
task ends up cheaper — that is still the unrun benchmark.

## Not yet measured

The four-arm comparison (A–D), TRR, TTS, PEI and Task Success Rate in
[How performance will be proven](docs/06-benchmark-plan.md). The single A/B run
above covers one cell of that grid (roughly arms B vs C, on one task, n=1) and
does not substitute for it. Those need real model runs, and the stop criteria in
[Is this worth building — the honest case](docs/10-is-it-worth-building.md) are
decided from them.
