# Chat Commands

Hestia understands a small set of slash commands you can send in any chat surface
(CLI, Telegram, Matrix). Send `/help` in your client for the authoritative,
up-to-date list; this guide focuses on the ones worth knowing.

## `/compact` — compact the current session

Over a long session the conversation can grow large enough that the local model
spends a long time on prompt processing before each reply. `/compact` compacts
the current session **in place** without ending it:

- It replaces the older history with a task-aware summary (goal, criteria,
  progress, key findings, artifact paths) plus the last few turns verbatim.
- The original messages are archived and recoverable, never hard-deleted.
- It frees context and speeds up subsequent turns (the next turn pays a one-time
  KV-cache rebuild, then runs faster on the smaller history).
- Key task-state facts are also flushed to long-term memory.

You can steer what it preserves:

```
/compact
/compact keep the job search criteria and the resume path
```

Plain `/compact` uses the default task-aware behavior; `/compact <instruction>`
biases the summary toward your instruction.

Compaction can be tuned or disabled via `HESTIA_COMPACTION_*` (see
[environment variables](environment-variables.md)); it skips sessions shorter
than `HESTIA_COMPACTION_MIN_MESSAGES`.

## Other commands

- `/reset` — start a fresh session (the previous one is archived, and its handoff
  summary carries forward).
- `/help` — list the available commands in your client.

A few additional inspection commands exist (`/session`, `/history`, `/refresh`,
`/tokens`); run `/help` for the current set and their descriptions, since they
can change between releases.

## Related

- [Long-term memory](memory.md) — how compaction and archival feed memory.
