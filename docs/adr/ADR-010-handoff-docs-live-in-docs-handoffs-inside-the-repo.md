# ADR-010: Handoff docs live in `docs/handoffs/` inside the repo

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** Phase 1a report was written to a hermes-context-audit folder outside
  the repo. This makes version history fragmented and risks loss when the external
  folder is cleaned up.
- **Decision:** All Hestia phase reports and handoff documentation live in
  `docs/handoffs/` inside the repository, committed with each phase.
- **Consequences:** Phase reports are versioned with the code they describe.
  Repository size grows slightly with each phase report (acceptable).
