# Kimi — current task (orchestration pointer)

**Orchestrator:** Kimi (self-orchestrating via subagents)
**Last set by:** Kimi — 2026-11-03

---

## Status

L248–L250 + #89 are **merged to develop, deployed to runtime, and released as
v0.17.0** (tag on develop @ `70e2147e`, pushed; CHANGELOG + release notes
landed). Cards #86–#89 are In Review awaiting Dylan's Done.

- Merged develop: stream-state fix, descriptive error messages, `/thinking`
  toggle, coder-bot non-routed-chat logging, plus the prepped v0.17.0 content
  (L232–L234, TTS device, `/intro`, etc.). Merged-develop gates: 2573 passed.
- Runtime (`~/Hestia-runtime`) now runs a dedicated `runtime` branch tracking
  `origin/develop` (shared git dir with `~/Hestia`; develop stays checked out
  in `~/Hestia`). Uncommitted WIP preserved across the move: card #65 (TTS)
  and card #83 (browser-stream) — both deliberately uncommitted per the
  v0.17.0 release prep.
- `operator_user_id=8550496999` set in `config.runtime.py` (env-overridable);
  Timo (8569861468) defaults to hidden thinking.
- Runtime gates green (2584 passed); `hestia-serve` + `hestia-tg-agent`
  restarted healthy; migration m013 applied.

## Next

- **Dylan:** open the develop→main PR and merge to finalize v0.17.0 on main
  (gh isn't authenticated in the agent shell; tag v0.17.0 is already pushed).
- **Post-release rule:** v0.17.0 is tagged on develop — no feature merges to
  develop until a new release-prep doc exists (release discipline).
- Smoke-test live: `/thinking` toggle persistence, descriptive error format,
  and a turn that streams narration before its first tool call (L249 shape).
- Outstanding WIP: card #65 (TTS) and card #83 (browser-stream) remain
  uncommitted in the runtime worktree.
