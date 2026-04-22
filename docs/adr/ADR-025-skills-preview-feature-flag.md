# ADR-025: Skills Preview Feature Flag

## Status

Accepted (v0.7.11)

## Context

The skills framework (`@skill` decorator, `SkillRegistry`, `hestia skill *` CLI, DB table) is fully implemented but **not yet wired into the orchestrator's turn loop**. A user who discovers the `@skill` decorator or the CLI commands could reasonably expect that defining a skill makes it available to the model during conversation. Without integration, the framework silently no-ops: skills are stored but never invoked.

For a public release, silent no-op behavior on a visible feature is confusing and damages trust. Two alternatives were considered:

1. **Hide the code entirely** — remove the decorator, CLI group, and table until integration is ready. This discards working code and complicates the integration branch.
2. **Gate behind an explicit opt-in flag** — keep the code visible and functional, but require the user to set an environment variable before any skill-related surface becomes active. This signals "preview" clearly while preserving the implementation.

## Decision

All public skills surfaces raise `ExperimentalFeatureError` unless `HESTIA_EXPERIMENTAL_SKILLS=1` is set in the environment.

- `@skill` decorator raises on application.
- `hestia skill *` CLI commands print an informative error to stderr and exit non-zero.
- The error message points to `README.md#skills` for context.

The env-var name `HESTIA_EXPERIMENTAL_SKILLS` follows the existing `HESTIA_*` prefix convention. The value `1` is used instead of a boolean-like string to avoid ambiguity with empty-string defaults.

## Consequences

- Users who write `@skill` without opting in get immediate, actionable feedback.
- Tests that exercise the decorator must set the env var (or use `monkeypatch`).
- When skills are wired into the orchestrator, the gate will be removed or replaced with a runtime capability check.
