# Development Process Archive

This directory contains the operational records of how Hestia was built using an
AI-assisted workflow. **It is historical**, not current operating documentation.
For current architecture, see [`../adr/`](../adr/) and [`../README.md`](../README.md).

## The build workflow

Hestia was built incrementally using a three-tool loop:

- **Cursor** (or Claude/Cowork) — code review, prompt authoring, per-loop merge
  decisions and orchestration.
- **Kimi** — autonomous executor. Reads a single loop spec (`kimi-loops/L*.md`),
  implements every section, runs tests, commits, signals completion via a
  `.kimi-done` artifact.
- **Dylan (human)** — direction, secrets, final pass before public push and
  release tagging.

Each numbered loop (L01–L52+) corresponds to one focused work session: a single
spec file, a single feature branch, a single merge to `develop` after green
review. After ~16 loops the project reached `v0.2.0` (first public release);
subsequent loops shipped v0.8.0, v0.9.0, v0.9.1, and the voice + multi-user
feature arcs.

## What's here

| Path | What |
|------|------|
| `kimi-loops/L*.md` | One spec per loop. Names the sections to implement, sketches code, lists tests, and defines the `.kimi-done` contract. Immutable once the loop is merged. |
| `kimi-phase-queue.md` | Top-level ordering of all loops. |
| `kimi-loop-log.md` | Per-loop narrative: what Kimi did, what Cursor reviewed, what was merged. Newest entries at the top. |
| `prompts/KIMI_*.md` | Earlier prompt formats (pre-loop-spec era), kept for reference. |
| `design-artifacts/`, `reviews/` | One-off design and review notes from the build. |

Older per-phase handoff reports (Phase 1a–L15) were archived to a private
location outside this repository during L16.

## Why keep this in the public repo?

Transparency about how the project was built — which models, which workflow,
how much was AI-driven vs. human-driven, where the failure modes were. Anyone
trying to reproduce the methodology has the full record.

If you are only interested in *using* Hestia, ignore this directory entirely.

## mypy baseline

`mypy-baseline.txt` lists the 44 pre-existing mypy errors as of v0.2.1.
CI fails on any *new* error. To fix one of these baseline errors, fix it in the
source and remove the matching line from the baseline in the same commit.
