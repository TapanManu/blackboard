# Measured Results — L0 + L1

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
L1 skill prompt, which is loaded once per session instead of re-sent every turn.
Real measurement afterwards: 395.

## Bugs the tests found before any agent did

| Bug | Found by | Fix |
|---|---|---|
| Concurrent writers of identical content raced on one `.tmp` path and renamed a vanished file | `test_concurrent_identical_artifact_writes_converge` | per-writer unique temp name |
| `export` → `import` into a different workspace was rejected, making a "portable dump" unportable | `test_cli.py` | rebase the workspace segment on import; `--keep-workspace` for exact restore |
| `topic/**` did not match the bare topic itself | `test_uri.py` glob table | `/**` compiles to `(?:/.*)?` |

## Not yet measured

Everything in `docs/06-benchmarks.md` — arms A/B/C/D, TRR, TTS, PEI, Task Success
Rate, coordination overhead. Those need real model runs, and the kill criteria in
`docs/09-value.md` are decided from them. Nothing here says the board is worth it
on a real task; it says the store does what it claims, at the cost it claims.
