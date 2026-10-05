# Claude Code adapter

Apply after [`../../SETUP.md`](../../SETUP.md) steps 1–3. Two pieces of plumbing: a hook that states
the board contract on every subagent spawn, and a worker agent whose tools are scoped to the board.

`<repo>` below is this repository's absolute path. `<ws>` is the workspace name.

---

## Skills

Claude Code discovers skills in `~/.claude/skills/<name>/SKILL.md` (all projects) or
`<project>/.claude/skills/` (one project, committed with the repo). Symlink rather than copy, so
repo edits take effect without reinstalling:

```bash
ln -s <repo>/skills/blackboard          ~/.claude/skills/blackboard
ln -s <repo>/skills/blackboard-parallel ~/.claude/skills/blackboard-parallel
ln -s <repo>/skills/session-handoff     ~/.claude/skills/session-handoff
```

Each skill's `description` triggers it on relevant work, so none of them costs anything on a session
that never fans out or parks a task.

## MCP server

`<project>/.mcp.json` (per project) or via `claude mcp add`. Shape in
[`../../.mcp.json.example`](../../.mcp.json.example). Two failure modes worth restating: `--workspace`
goes **before** `serve`, and the env vars are `BLACKBOARD_TOKEN` / `BLACKBOARD_ROLE`.

Reconnect with `/mcp` after editing. A server edited mid-session stays disconnected until then.

## Spawn-time contract (hook)

Merge [`settings.hook.json`](settings.hook.json) into `<project>/.claude/settings.local.json` — the
personal, git-ignored file, not the committed `settings.json`, since the board is per-machine.

It is a `PreToolUse` hook matching `Task`. It fires on **every** spawn, including `Explore` and
general-purpose agents where the board is often the wrong choice — which is why its text says to
skip the board for small results. Replace `bb://sedai/` with your own workspace before using it.

Verify:

```bash
jq -e '.hooks.PreToolUse[] | select(.matcher=="Task") | .hooks[] | .command' \
  <project>/.claude/settings.local.json
```

Exit 0 and your command printed = correct nesting. **The hook will not fire until config reloads** —
open `/hooks` once, or restart the session. A malformed `settings.local.json` silently disables every
setting in that file, so validate before relying on it.

Narrow it with the hook's `if` field, or drop it entirely and rely on the worker agent, if it proves
noisy on quick spawns.

## Compaction checkpoint (hooks)

**The problem:** when Claude Code compacts a long session, it replaces the transcript with a
summary. Unless the agent wrote its state to the board first, the branch it was on, its uncommitted
files and the summary are not stored anywhere a later session can read.

The same [`settings.hook.json`](settings.hook.json) adds two hooks that save this without the agent
having to remember:

| Hook | Writes to `bb://<ws>/run/state/compact-<session id>` |
|---|---|
| `PreCompact` | Git branch, last commit, up to 50 uncommitted files, last 5 commits |
| `PostCompact` | Appends Claude Code's compaction summary and makes it the entry's short summary |

Each compaction in the same session adds a new version of that entry, so earlier ones stay
readable. The hooks print nothing, so they add no tokens to the session. They never block
compaction: any error is written to stderr and the hook still exits 0.

Workspace comes from `BLACKBOARD_WORKSPACE` (default `default`); set it in the hook's `env`, or
change the command to `blackboard-mcp -w <ws> hook pre-compact`. `blackboard-mcp` must be on the
`PATH` Claude Code runs hooks with.

Read the checkpoint back with `blackboard-mcp -w <ws> get bb://<ws>/run/state/compact-<session id>`.

**Limit:** this has not yet been run against a live compaction. The `compact_summary` field it reads
is the one another Claude Code plugin (Navigator) documents; if it is missing, the checkpoint keeps
only the git state.

## Command-line reads and writes

`put`, `get`, `search` and `resume` reach the board without the MCP server, for scripts and hooks.
They act as the machine's owner (full access to the workspace), because anyone who can run them can
already open the database file.

```bash
blackboard-mcp -w ws put bb://ws/run/decision/d1 --body '{"why":"derived"}' --digest "skip generated files"
blackboard-mcp -w ws get bb://ws/run/decision/d1 --mode full
blackboard-mcp -w ws search "SED-123"
blackboard-mcp -w ws resume          # the three reads a fresh agent starts with, one JSON line each
```

## Worker agent

Copy [`agents/board-worker.md`](agents/board-worker.md) to `<project>/.claude/agents/board-worker.md`
(or `~/.claude/agents/` for all projects), then edit its `bb://` URIs to your workspace.

Spawn it with `subagent_type: "board-worker"`. Its prompt carries the whole contract, so the parent
pays nothing for it. Give it its lane and output URI in the spawn prompt — it is told to ask rather
than guess.

## What this adapter cannot do

- **Monitors and background shells.** Their output arrives as tool results before anything could
  file it. The fix is shell hygiene — redirect to a file, then `update_state(source_path=...)` — not
  a hook.
- **Built-in agent types.** `Explore` and `general-purpose` do not carry the worker prompt; they get
  only the hook's two lines.
- **Suppressing a tool result.** A `PostToolUse` hook of type `mcp_tool` can file a tool response to
  the board automatically, but the parent has already received that result. Auto-filing is
  bookkeeping, not a saving.
