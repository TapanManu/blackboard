# A/B run 2 — the five questions

Run date 2026-09-08, at `cb8c432`. Re-run of the 2026-09-07 A/B against the write
path added in `526c4c0`..`cb8c432` (`append`, `columns`/`rows`, `digest_from`,
digest-only entries, `select`/`lines`, `writes`).

The 2026-09-07 prompts were never committed — they existed only in a transcript,
which is the flaw this file exists to fix. These five are written to the same
shape as the originals (docs contradictions, module load-bearing, test coverage,
setup-bundle consistency, deferred-layer triggers) but they are **not** the same
text, so the comparison to that run is indicative, not direct.

## Control

Both arms get a byte-identical task block. Only the reporting instruction
differs. Same model, same agent type (`general-purpose`), five lanes each, all
five launched in one message so they run concurrently.

## Task block (identical in both arms)

> You are analysing the repository at `/Users/tapan/petprojects/blackboard`. Read
> only that directory. Question: **{QUESTION}** Work to a thorough standard: read
> the relevant source and docs, verify every claim against the code as it is now,
> and cite `file:line` for each finding. Distinguish what you verified from what
> you inferred.

## Lanes

| Lane | Question |
|---|---|
| `docs` | Where do the design docs in `docs/` contradict what the code actually does? |
| `modules` | Which modules in `src/blackboard/` are load-bearing and which are incidental — what would break if each were removed? |
| `tests` | What behaviour in `src/blackboard/` is untested, and which of those gaps could hide a real defect? |
| `setup` | Do `SETUP.md`, `.mcp.json.example`, `pyproject.toml` and `integrations/` agree with each other and with the code? |
| `layers` | Per `docs/08-scope-and-layers.md`, what concrete condition should trigger building each deferred layer, and is anything already past its trigger? |

## Reporting — Arm A (no board)

> Report your findings as a detailed prose report in your final message. Before
> finishing, write that exact same text to `bench/armA/{LANE}.md`. Do not use any
> blackboard or `bb://` tool.

## Reporting — Arm B (board)

> Report by writing to the Blackboard. Load the skill at
> `~/.claude/skills/blackboard/SKILL.md` first and follow it. Write your findings
> to `bb://sedai/bench.{LANE}/result/exp2` with an authored digest, choosing the
> cheapest write shape that fits: `columns`+`rows` for a findings list,
> `digest_from` if the body already carries a summary, a digest alone if the whole
> finding is under ~200 tokens, `source_path` with `select`/`lines` for content
> that already exists in a file. Then reply to me in at most three lines: the URI,
> the entry's `est_tokens`, and a one-sentence headline. Before finishing, write
> that exact three-line reply to `bench/armB/{LANE}.txt`.

## What is measured

| Measure | How |
|---|---|
| Parent context | `est_tokens` (cl100k_base) over the reply each agent returned, captured verbatim in `armA/` and `armB/` |
| Digest read-back | `est_tokens` over the `get_state` results the parent reads in Arm B |
| Wall clock | epoch seconds around each arm's launch |
| Internal agent spend | **not measured** — no per-agent token accounting is available from inside the session |
