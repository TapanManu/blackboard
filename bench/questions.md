# A/B run 2 — the five questions

Run date 2026-09-08, at `cb8c432`. Re-run of the 2026-09-07 A/B against the write
path added in `526c4c0`..`cb8c432` (`append`, `columns`/`rows`, `digest_from`,
digest-only entries, `select`/`lines`, `writes`).

The 2026-09-07 prompts were never committed — they existed only in a transcript,
which is the flaw this file exists to fix. These two are written to the same
shape as two of the originals (docs contradictions, test coverage) but they are
**not** the same text, and there are two lanes rather than five. The comparison
to that run is indicative, not direct.

## Control

Both arms get a byte-identical task block. Only the reporting instruction
differs. Same model, same agent type (`general-purpose`), **two lanes** each,
both launched in one message so they run concurrently, arms run one after the
other so they do not contend for wall clock.

**Neither arm returns its findings to the parent.** The original run measured
Arm A by letting five prose reports land in the parent context, which is the
cost being measured -- paying it to measure it is what made the run expensive and
risky. Here every agent replies in at most three lines and puts its output
somewhere countable: Arm A in a file, Arm B on the board. The parent-context
figure for Arm A is then the size of the report it produced, counted with the
same tokenizer. Same number, without the parent holding it.

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
| `tests` | What behaviour in `src/blackboard/` is untested, and which of those gaps could hide a real defect? |

## Reporting — Arm A (no board)

> Write your full findings as a prose report to `bench/armA/{LANE}.md` — the
> report you would have written into a reply, at the same depth. Then reply in at
> most three lines: the path, the file's size in bytes, and a one-sentence
> headline. Do not paste the report into your reply. Do not use any blackboard or
> `bb://` tool.

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
| Arm A parent context | `est_tokens` (cl100k_base) over `armA/{lane}.md` — the report that would have been returned |
| Arm B parent context | `est_tokens` over the three-line reply plus the parent's `get_state` digest read |
| Digest read-back | `est_tokens` over the `get_state` results the parent reads in Arm B |
| Wall clock | epoch seconds around each arm's launch |
| Internal agent spend | **not measured** — no per-agent token accounting is available from inside the session |
