# Is this worth building — the honest case

**For:** anyone with five minutes. What is actually proven, what was claimed and
then dropped, and the five measurements that would say *stop*.

New here? Read [the README](../README.md) first — it explains what the board is
and defines the handful of terms used below.

---

## The claim being defended

> A shared, local store where every note carries a short summary lets an agent's
> work survive its session ending, and lets several agents avoid redoing each
> other's work — at an overhead low enough to be worth it on jobs with more than
> about five parts.

That is narrower than the project started out claiming. It is also defensible,
measurable in a week, and not provided by anything else in the toolchain today.

## Three sources of value, ranked by how confident we are

### 1. Picking up where a stopped session left off — high confidence, and unique

Today, hitting a context limit, crashing, or closing the terminal destroys the
work. Nothing else in the toolchain recovers it.

A fresh agent reads three things — the goal and constraints, what is done and in
flight, and the last ten decisions with their reasoning — and is ready to work.
**Measured at 2,679 tokens, and that figure does not grow as the project does.**

The decisions matter most. They are what a fresh agent otherwise re-argues from
scratch, having no idea the question was already settled.

This alone justifies building the store. It needs no second agent, no task
queue, and no trust scoring.

### 2. Not redoing work another agent already did — high confidence

This is what actually produced the win in [the wiki incident](https://collusion.wiki/)
that inspired the project: don't recompute what someone else already computed.
Two sessions resolving the same dependency; two agents analyzing the same module;
a procedure that gets re-derived every week.

Writing a note, reading it back, and searching for it is the whole mechanism.

### 3. Keeping per-step cost flat — medium confidence, still unmeasured

The reasoning is sound: without a shared store, an agent re-reads a transcript
that only grows, so a long job costs disproportionately more the longer it runs.
With one, each step reads a fixed handful of summaries instead.

But the overhead is real and paid up front — see
[what the board actually costs you](09-what-it-costs-you.md). Whether the trade
comes out ahead is an experiment, not an argument. **Do not claim this before the
comparison in [the benchmark plan](06-benchmark-plan.md) has been run.**

---

## Claims that were dropped

Being specific about what was withdrawn is part of the case for what remains.

| Dropped claim | Why |
|---|---|
| **"Constant-time lookups"** | It is constant *per step*. Database lookup speed was never the bottleneck. Stated without that qualifier, it is the fastest way to lose a technical reader. |
| **"~88% token savings, 4.7× faster"** | Invented. No experiment produced those numbers. [Measured results](../MEASURED.md) now contains only figures a test actually generated. |
| **"Validated by the OpenAI agent wiki"** | Those agents were pooling benchmark answers and working around a sandbox, not conserving context. The wiki is evidence of *demand* — agents built a shared board when none existed — not an endorsement of this design. |
| **Trust scoring as a headline feature** | It is a weighted guess wearing a number. Useful later; not a reason to adopt anything today. |

---

## What would mean *stop*

Run the store and its protocol for a week, then check these. **Two failures out of
five means the honest answer is no.** Writing them down now, while it is still
cheap to be objective, is what makes a positive result believable later.

| Measurement | Fails if | What it would mean |
|---|---|---|
| Tokens spent reading and writing the board, as a share of all tokens | above 15% | The board is not paying for itself. |
| Correctness compared to one agent working alone | worse by more than 2 percentage points | Summarizing is losing information that mattered. |
| How often an agent reads a summary and then needs the full note anyway | above 30% | The summaries are wrong-sized; you are paying for both. |
| A fresh agent taking over mid-job | fails, or needs more than 3,000 tokens | The one unambiguous win does not work. |
| Tokens saved versus simply copying context into cheaper agents | less than 25% | The board adds nothing over the obvious approach. |

That fifth row is the one people skip. Using cheap models instead of one
expensive model saves money *by itself* — so the comparison has to be against
that, not against a single expensive agent, or the board gets credit for a saving
it did not produce.

---

## Where it is the wrong tool

Publishing this list is what makes the positive claims credible. Something that
helps everywhere helps nowhere.

- Jobs with fewer than about five parts — the overhead exceeds the saving.
- Anything that fits comfortably in one context window.
- Strictly sequential work, where each step needs the full output of the last.
- Exploratory work you cannot yet break into pieces.
- A single session with no handoff and no risk of crashing.
- Content that cannot be broken up — one large file read start to finish.

---

## Verdict

**Yes, with the narrower claim and a one-week experiment to test it.**

Taking over a stopped session and avoiding duplicated work are real, currently
unmet, and cheap to build. Keeping per-step cost flat is plausible and testable.

The original six-week design guarded against failures nobody had observed.
Building only the store and the protocol tests the whole idea in a week, for
roughly a tenth of the effort. If the numbers land, everything held back remains
available and unblocked. If they do not, a week was spent instead of six.
