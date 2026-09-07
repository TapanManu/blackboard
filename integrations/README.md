# Integrations

The three skills in [`../skills/`](../skills/) are the portable half: any MCP-capable client can
load them as instruction files. An integration is the **non-portable** half — the mechanism a
specific client offers for making the board contract deterministic instead of model-decided.

| Client | Adapter |
|---|---|
| Claude Code | [`claude-code/SETUP.md`](claude-code/SETUP.md) |

No adapter for your client? The skills still work. The adapter only removes the "did the agent
remember to load the skill" failure mode.

---

## What an adapter must provide

Three things, in descending order of value.

**1. A spawn-time contract.** Whatever mechanism fires on every subagent spawn (a hook, a
middleware, a wrapper) should state: the agent's lane, its output URI, and that results are written
as digests rather than returned as prose. Keep it to a couple of lines — this text is paid for on
every spawn.

**2. A scoped worker definition.** If the client supports declaring agent types, declare one whose
tools are the five board tools plus whatever read-only access the work needs. That way the contract
travels in the worker's own prompt and costs the parent nothing.

**3. Install paths.** Where the client discovers instruction files, and whether they are per-user or
per-project. Say which, because it decides whether a teammate cloning the repo gets them.

## What an adapter must not do

- **Do not force board usage.** Auto-using the board for a pass/fail subagent costs more than it
  saves. The contract should say *how* to use the board, and leave *whether* to the model.
- **Do not inject board content into a system prompt or any pinned preamble.** It breaks the prompt
  cache on every read and turns the board into a net loss.
- **Do not fire a contract on every shell command.** A per-shell injection costs more than the
  output hygiene it is asking for.
- **Do not ship a literal token.** Use the client's variable substitution.

## Contributing one

Add `integrations/<client>/` with a `SETUP.md` written to an agent, plus any config fragments.
Register it in the table above. State plainly which of the three items your client cannot do — an
honest gap is more useful than a workaround that silently does nothing.
