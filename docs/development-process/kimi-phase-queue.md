# Kimi phase queue (Cursor advances `docs/development-process/prompts/KIMI_CURRENT.md` after each green review)

| Order | Branch (suggested) | Executor spec |
|-------|-------------------|----------------|
| 0 | `feature/phase-7-cleanup` | [`design-artifacts/kimi-hestia-phase-7-cleanup.md`](design-artifacts/kimi-hestia-phase-7-cleanup.md) |
| 1 | `feature/matrix-adapter` | [`kimi-loops/L01-matrix-adapter.md`](kimi-loops/L01-matrix-adapter.md) |
| 2 | `feature/phase-8a-identity-reasoning` | [`kimi-loops/L02-phase-8a-identity-reasoning.md`](kimi-loops/L02-phase-8a-identity-reasoning.md) |
| 3 | `feature/phase-8b-cli-exceptions-datetime` | [`kimi-loops/L03-phase-8b-cli-exceptions-datetime.md`](kimi-loops/L03-phase-8b-cli-exceptions-datetime.md) |
| 4 | `feature/phase-9-test-infra` | [`kimi-loops/L04-phase-9-test-infra.md`](kimi-loops/L04-phase-9-test-infra.md) |
| 5 | `feature/phase-10-memory-epochs` | [`kimi-loops/L05-phase-10-memory-epochs.md`](kimi-loops/L05-phase-10-memory-epochs.md) |
| 6 | `feature/phase-11-trace-store` | [`kimi-loops/L06-phase-11-trace-store.md`](kimi-loops/L06-phase-11-trace-store.md) |
| 7 | `feature/phase-12-skills` | [`kimi-loops/L07-phase-12-skills.md`](kimi-loops/L07-phase-12-skills.md) |
| 8 | `feature/phase-13-audit` | [`kimi-loops/L08-phase-13-audit.md`](kimi-loops/L08-phase-13-audit.md) |
| 9 | `feature/phase-14-cleanup-release-prep` | [`kimi-loops/L09-phase-14-cleanup-release-prep.md`](kimi-loops/L09-phase-14-cleanup-release-prep.md) |
| 10 | `feature/l10-matrix-realworld-runtime` | [`kimi-loops/L10-matrix-realworld-runtime-testing.md`](kimi-loops/L10-matrix-realworld-runtime-testing.md) |
| 11 | `feature/l11-test-tools-memory-mock` | [`kimi-loops/L11-test-tools-memory-mock.md`](kimi-loops/L11-test-tools-memory-mock.md) |
| 12 | `feature/l12-matrix-e2e-two-user` | [`kimi-loops/L12-matrix-e2e-two-user.md`](kimi-loops/L12-matrix-e2e-two-user.md) |
| 13 | `feature/l13-scheduler-matrix-cron` | [`kimi-loops/L13-scheduler-matrix-cron.md`](kimi-loops/L13-scheduler-matrix-cron.md) |
| 14 | `feature/l14-docs-runtime-manual` | [`kimi-loops/L14-docs-runtime-manual-smoke.md`](kimi-loops/L14-docs-runtime-manual-smoke.md) |
| 15 | `feature/l15-security-hardening` | [`kimi-loops/L15-security-bug-fixes.md`](kimi-loops/L15-security-bug-fixes.md) |
| 16 | `feature/l16-pre-public-cleanup` | [`kimi-loops/L16-pre-public-cleanup.md`](kimi-loops/L16-pre-public-cleanup.md) |
| 17 | *(develop + main)* | [`kimi-loops/L17-release-v0.2.0.md`](kimi-loops/L17-release-v0.2.0.md) |
| 18 | `feature/l18-post-public-cleanup` | [`kimi-loops/L18-post-public-cleanup-v0.2.1.md`](kimi-loops/L18-post-public-cleanup-v0.2.1.md) |
| 19 | `feature/l19-slot-save-and-ctx-alignment` | [`kimi-loops/L19-slot-save-and-ctx-alignment-v0.2.2.md`](kimi-loops/L19-slot-save-and-ctx-alignment-v0.2.2.md) |
| 20 | `feature/l20-trust-config-and-web-search` | [`kimi-loops/L20-trust-config-and-web-search.md`](kimi-loops/L20-trust-config-and-web-search.md) |
| 21 | `feature/l21-context-resilience-handoff` | [`kimi-loops/L21-context-resilience-handoff-summaries.md`](kimi-loops/L21-context-resilience-handoff-summaries.md) |
| 22 | `feature/l22-mypy-cleanup` | [`kimi-loops/L22-mypy-cleanup-and-ci-strictness.md`](kimi-loops/L22-mypy-cleanup-and-ci-strictness.md) |
| 23 | `feature/l23-platform-confirmation` | [`kimi-loops/L23-platform-confirmation-callbacks.md`](kimi-loops/L23-platform-confirmation-callbacks.md) |
| 24 | `feature/l24-injection-detection` | [`kimi-loops/L24-prompt-injection-detection-and-egress-audit.md`](kimi-loops/L24-prompt-injection-detection-and-egress-audit.md) |
| 25 | `feature/l25-email-adapter` | [`kimi-loops/L25-email-adapter-read-and-draft.md`](kimi-loops/L25-email-adapter-read-and-draft.md) |
| 26 | `feature/l26-reflection-loop` | [`kimi-loops/L26-reflection-loop-proposals.md`](kimi-loops/L26-reflection-loop-proposals.md) |
| 27 | `feature/l27-style-profile` | [`kimi-loops/L27-personality-that-learns-style-profile.md`](kimi-loops/L27-personality-that-learns-style-profile.md) |

**Chain index (L10–L14):** [`prompts/KIMI_LOOPS_L10_L14.md`](prompts/KIMI_LOOPS_L10_L14.md) · **Credentials:** [`docs/testing/CREDENTIALS_AND_SECRETS.md`](../testing/CREDENTIALS_AND_SECRETS.md)

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
