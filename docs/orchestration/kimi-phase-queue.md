# Kimi phase queue (Cursor advances `docs/prompts/KIMI_CURRENT.md` after each green review)

| Order | Branch (suggested) | Executor spec |
|-------|-------------------|----------------|
| 0 | `feature/phase-7-cleanup` | [`docs/design/kimi-hestia-phase-7-cleanup.md`](../design/kimi-hestia-phase-7-cleanup.md) |
| 1 | `feature/matrix-adapter` | [`kimi-loops/L01-matrix-adapter.md`](kimi-loops/L01-matrix-adapter.md) |
| 2 | `feature/phase-8a-identity-reasoning` | [`kimi-loops/L02-phase-8a-identity-reasoning.md`](kimi-loops/L02-phase-8a-identity-reasoning.md) |
| 3 | `feature/phase-8b-cli-exceptions-datetime` | [`kimi-loops/L03-phase-8b-cli-exceptions-datetime.md`](kimi-loops/L03-phase-8b-cli-exceptions-datetime.md) |
| 4 | `feature/phase-9-test-infra` | [`kimi-loops/L04-phase-9-test-infra.md`](kimi-loops/L04-phase-9-test-infra.md) |
| 5 | `feature/phase-10-memory-epochs` | [`kimi-loops/L05-phase-10-memory-epochs.md`](kimi-loops/L05-phase-10-memory-epochs.md) |
| 6 | `feature/phase-11-trace-store` | [`kimi-loops/L06-phase-11-trace-store.md`](kimi-loops/L06-phase-11-trace-store.md) |
| 7 | `feature/phase-12-skills` | [`kimi-loops/L07-phase-12-skills.md`](kimi-loops/L07-phase-12-skills.md) |
| 8 | `feature/phase-13-audit` | [`kimi-loops/L08-phase-13-audit.md`](kimi-loops/L08-phase-13-audit.md) |

**Authoritative detail** for Phases 8–13 lives in [`docs/design/hestia-phase-8-plus-roadmap.md`](../design/hestia-phase-8-plus-roadmap.md). Each `L*.md` file names sections to implement and the **`.kimi-done`** contract.

**Matrix product design** for loop 1: [`docs/design/matrix-integration.md`](../design/matrix-integration.md).

After each loop: merge to `develop` when green, bump queue in `KIMI_CURRENT.md`, append [`kimi-loop-log.md`](kimi-loop-log.md).

### Review carry-forward (required before the next Kimi run)

When Cursor advances the queue, open the **upcoming** `kimi-loops/L*.md` (the file `KIMI_CURRENT` will point at next) and add or update:

```markdown
## Review carry-forward

- …
```

List **every** issue from the prior loop’s review: bugs, missing tests, style smells, confusing names, debt worth fixing now. Kimi treats this section as part of the task for that loop. If nothing to carry: `- *(none)*`.
