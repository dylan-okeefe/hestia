# How Hestia is Built

Hestia is developed by one human operator and two AI agents running in a
deliberately disciplined loop. The process is as much the point as the code: it
lets a solo maintainer ship large, safety-sensitive subsystems (a trust boundary,
a concurrency model, an automated memory-maintenance system) without the usual
solo-project failure modes, by keeping a human in the decision and approval seats
and putting a second set of eyes on every change before it lands.

This document describes that process. It doubles as onboarding for a contributor
and as a record of how the work actually gets done.

## Roles

- **Operator (Dylan).** Owns decisions, approvals, merges to `main`, secrets, and
  releases. Sets direction; resolves the design questions that only a human can.
- **Implementer (Kimi).** Writes the code. Runs in iterative loops on the
  development box against an unambiguous spec, on a feature branch, behind quality
  gates. Never merges without approval.
- **Advisor/reviewer (Claude).** Produces specs, runs decision passes, and reviews
  branches against the spec and invariants. Advises and reviews; does not write
  production code.

The implementer and the advisor run on different machines. Kimi codes on the dev
box; the advisor sees the operator's clone, which lags until the operator pulls.
Status therefore lives in a shared board (see below), not in any one machine's
working tree.

## The unit of work: a loop

A **loop** is one coherent change. It moves through a fixed lifecycle, which is
also the board's columns:

1. **Identified.** A need surfaces (a review finding, a feature, a bug).
2. **Decision pass.** Before any code on a non-trivial or risky change, the open
   design questions are surfaced and resolved by the operator (with the advisor),
   and recorded in a `decisions-*.md`. Nothing ambiguous is left for the
   implementer to guess.
3. **Spec'd.** An unambiguous implementation plan lands in the repo
   (`spec-*.md` / a numbered loop doc), including the invariants and the tests
   that must pass.
4. **In progress.** The implementer builds it on a feature branch, writes the
   failing test that asserts each invariant first, makes it pass, runs the full
   gates (pytest, mypy, ruff, web-ui build), and stops. It does not merge.
5. **In review.** The advisor reviews the branch diff against the spec, the
   decisions, and the invariants, verifying the code, not the "done" labels.
   Findings go back; fixes; re-review. The operator gives the merge nod.
6. **Done.** Merged to `develop`. Releases go `develop` → `main` via PR, tagged,
   deployed, and restarted, with the changelog, ADRs, and upgrade notes kept
   current.

## The guardrails that make it safe

These are the rules that turn "an AI wrote a lot of code overnight" into
something trustworthy:

- **Decisions before code.** Design forks are resolved by the operator and
  written down first. The implementer never guesses at an ambiguous spec.
- **Tests assert invariants, first.** Each loop writes the test that proves the
  thing it claims to do (two concurrent turns serialize; a workflow node hits the
  confirmation gate) before implementing.
- **No silent skips.** Anything specified is mandatory. If a piece is too large to
  finish, it is split into a named follow-up loop and flagged, never quietly
  dropped. Every handoff carries a per-item accounting table mapping each spec
  item to done or deferred-to-loop.
- **Supervised review verifies code, not status.** Green gates and a "done" table
  can hide a missing safety net; one real review caught a concurrency loop that
  passed its own tests while silently omitting the two hardest guards. The review
  reads the diff against the invariants, and the no-silent-skip rule above was
  added to the process in direct response.
- **Risky changes are human-gated.** Trust/security behavior, schema-altering
  migrations, and anything destructive get a decision pass and a supervised review
  before they land. Destructive operations are reversible by construction
  (soft-delete with retention, undo, an auditable trace).
- **Decisions are recorded.** Architectural decisions are captured as append-only
  ADRs; when one is superseded, a new ADR references it rather than rewriting
  history.

## Where the record lives

- **Git holds the substance.** Specs, decision records, handoffs, per-item
  accounting, and ADRs live in the repo and are reviewed alongside the code. This
  is the durable, portable record.
- **The board (TaskView) holds the status.** It tracks where each loop sits in the
  lifecycle and links each card back to its repo docs. It is the live coordination
  surface; it does not replace the documentation.

The split is deliberate: the working surface can change or be replaced, but the
record of what was decided and why stays version-controlled with the code.

## Where to read the actual record

- `docs/reviews/` — specs, decision records, and review findings.
- `docs/adr/` — the architecture decision records.
- `docs/development-process/` — loop docs and cross-session handoffs (project
  archaeology, not user docs).
- `CHANGELOG.md`, `docs/releases/`, `UPGRADE.md` — what shipped, and how to move
  between versions.

## Worked examples

- **Trust, concurrency, and persistence (the `develop`-review arc).** A deep
  review surfaced two criticals: no single enforced trust boundary, and no
  per-session concurrency model. Each became its own decision pass, spec,
  implementation, and supervised review, landing the unified `CapabilityGate`, the
  session lock, and the store split. This arc is where the no-silent-skip rule was
  learned and added. See ADR-040 through ADR-046 and the matching specs/decisions.
- **The memory lifecycle.** In-session `/compact`, session-end fact extraction, and
  the reversible overnight memory-maintenance system (dedupe, prune, and
  confidence-gated supersession, all soft-delete with undo). This arc shows the
  reversible-by-construction approach to a destructive automated operation, and the
  brainstorm → decision-pass → spec flow for the in-progress topic-scoped memory
  design. See ADR-047 through ADR-049.
