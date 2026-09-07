  1. MEASURED.md — new section, placed after "The headline"

  The file's whole discipline is "numbers from the test suite with an exact
  tokenizer." This isn't that, so it gets its own section with the distinction
  stated up front:

  ## One live A/B run — not from the test suite

  Everything above comes from `pytest`. This section does not: it is a single
  live run
  on 2026-09-07, with real agents doing real analysis, recorded because
  [the benchmark plan](docs/06-benchmark-plan.md) had produced nothing yet and a
  one-off is better than an assumption. **n=1.** Treat it as a data point, not a
  result.

  **Task:** five agents, five questions about this repository (docs
  contradictions,
  module load-bearing analysis, test coverage, setup-bundle consistency,
  deferred-layer
  triggers). Identical prompts and identical requested depth in both arms; only
  the
  reporting path differed. Arm A returned prose. Arm B wrote a digest plus body
  to
  `bb://sedai/tasks.<lane>/result/exp1` and replied in three lines.

  | | Arm A (no board) | Arm B (board) | Delta |
  |---|---|---|---|
  | Parent context | 36,766 tok | **2,357 tok** | **-93.6%** |
  | — agent replies | 36,766 | 957 | |
  | — digest read-back | 0 | 1,400 | |
  | Internal agent spend | 607,120 tok | 372,112 tok | -38.7% |
  | Wall clock, slowest agent | 483 s | 376 s | -22.2% |

  Arm B also kept what it found: 20,895 tokens of full bodies on the board,
  addressable
  for the 1,400 spent reading five digests.

  **Quality parity held.** Both arms independently found the same core defects.
  Arm B
  additionally found three Arm A missed: `.mcp.json.example`'s `uvx --from .`
  omits the
  `mcp` extra; `server.py:125` resolves the grant once at process start, so
  revoke and
  TTL are inert for a running server; `vacuum` scopes its live set to one
  workspace
  while artifacts are shared across all of them.

  **A prediction this run falsified.** The expectation was that Arm B would cost
  *more*
  internally, since each worker loads ~2,600 tokens of skill and schema before
  starting.
  It cost 39% less — composing a 9,500-token prose report is more expensive than
  writing
  a digest plus a body, and the write cost dominates the load cost.

  **What this does not establish.** One run, one repo, one task shape. No
  repetition, so
  run-to-run variance is unmeasured. Both arms used the same model, so this
  isolates the
  reporting path and nothing else. Arm A's prose is richer per finding than Arm
  B's
  digest — the honest claim is that the digests answered the same questions *at 
  decision
  level*, with detail retrievable at 3,000-6,000 tokens per entry. The four-arm
  design
  in `docs/06` (n=5 paired, Task Success Rate as a gate) remains unrun.

  And the "Not yet measured" section changes from listing everything in docs/06
  to:

  ## Not yet measured
  
  The four-arm comparison (A-D), TRR, TTS, PEI and Task Success Rate in
  [How performance will be proven](docs/06-benchmark-plan.md). The single A/B
  run above
  covers one cell of that grid (roughly arms B vs C, on one task, n=1) and does
  not
  substitute for it.

  2. README.md — two edits

  "Honest limits" currently says the board "has not been shown to make a real
  multi-agent task cheaper or faster overall." That's now too strong.
  Replacement:

  **What is proven and what is not.** The board demonstrably does what it claims
  at the
  cost it claims. One live five-agent A/B run has now been recorded — 93.6% less
  parent
  context, 39% less total agent spend, no quality loss ([Measured 
  results](MEASURED.md))
  — but that is a single run on this repository, not the four-arm benchmark in
  [docs/06](docs/06-benchmark-plan.md), which remains unrun. One data point is
  not a
  demonstration.

  "Does it work?" gains one row after the existing table:

  | Five agents, one task, live A/B | **93.6% less** parent context (36,766 ->
  2,357 tok), n=1 |

  What I'd flag before you say yes

  The MEASURED.md numbers all reproduce from pytest; anyone can re-run them.
  This one cannot be reproduced — it depended on a live session, a specific
  model, and prompts that exist only in my transcript. That's a real break with
  the file's standard. Two ways to handle it: label it as I have, or
  additionally commit the ten prompts and the raw measurements to bench/ so
  someone could repeat the shape of it.

  I'd also fix the three defects the run surfaced in the same commit, since two
  of them are in files I shipped today. Say the word and I'll write it up.
