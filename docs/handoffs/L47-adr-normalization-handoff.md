# L47 — ADR Normalization Handoff

**Status:** Complete  
**Branch:** `chore/l47-adr-normalization`  
**Scope:** Consolidate hybrid ADR system into single consistent structure.

---

## What changed

### 1. ADR audit

| Location | Count | Notes |
|----------|-------|-------|
| `docs/DECISIONS.md` (inline) | 21 | ADR-001 through ADR-021, short bullet format |
| `docs/adr/` (separate files) | 11 | Mixed 3- and 4-digit numbering; collisions |
| `docs/architecture/adr/` | 1 | Orphaned ADR-023 |

**Collisions found:**
- ADR-014/015/017–021 existed in both `DECISIONS.md` **and** `docs/adr/` with **different topics**
- Two ADR-022s in `docs/adr/` (skills preview vs. identity)
- ADR-023 was in wrong folder (`docs/architecture/adr/`)

### 2. Normalization — all numbers now 4-digit, zero-padded, unique

**Renumbered existing separate-file ADRs:**
| Old | New | Topic |
|-----|-----|-------|
| `ADR-022` | `ADR-0025` | Identity as compiled view |
| `ADR-024` | `ADR-0024` | Skills as user-defined functions (zero-padded filename) |
| `ADR-023` | `ADR-0023` | Memory epochs (moved from `docs/architecture/adr/`) |

**Migrated `DECISIONS.md` inline ADRs to `docs/adr/`:**
| Old | New | Topic |
|-----|-----|-------|
| ADR-001 | ADR-0001 | Project name is "Hestia" |
| ADR-002 | ADR-0002 | Package manager is `uv` |
| ADR-003 | ADR-0003 | Language is Python 3.11+ |
| ADR-004 | ADR-0004 | Persistence: SQLAlchemy Core + SQLite/Postgres |
| ADR-005 | ADR-0005 | Subagents in same process |
| ADR-006 | ADR-0006 | Search is FTS-only at first |
| ADR-007 | ADR-0007 | No web UI in v1 |
| ADR-008 | ADR-0008 | License is Apache 2.0 |
| ADR-009 | ADR-0009 | count_request correction factor (superseded) |
| ADR-010 | ADR-0010 | Handoff docs in repo |
| ADR-011 | ADR-0011 | Calibration: two numbers |
| ADR-012 | ADR-0012 | Turn state machine |
| ADR-013 | ADR-0013 | SlotManager LRU eviction |
| ADR-014 | ADR-0027 | Scheduler via Orchestrator *(renumbered to avoid collision)* |
| ADR-015 | ADR-0028 | HestiaConfig dataclass *(renumbered)* |
| ADR-016 | ADR-0016 | Telegram adapter HTTP/1.1 + rate limits *(no collision)* |
| ADR-017 | ADR-0029 | FTS5 memory, no vector search *(renumbered)* |
| ADR-018 | ADR-0030 | Subagent delegation *(renumbered)* |
| ADR-019 | ADR-0031 | Capability labels *(renumbered)* |
| ADR-020 | ADR-0032 | Typed failure bundles *(renumbered)* |
| ADR-021 | ADR-0033 | Matrix adapter *(renumbered)* |

**Existing 4-digit ADRs kept unchanged:**
- ADR-0014 Context resilience
- ADR-0015 llama-server coexistence
- ADR-0017 Prompt-injection detection
- ADR-0018 Reflection loop
- ADR-0019 Style profile vs. identity
- ADR-0020 CLI decomposition
- ADR-0021 ContextBuilder prefix registry
- ADR-0022 Skills preview feature flag
- ADR-0026 Discord voice architecture

### 3. `DECISIONS.md` replaced with index

`docs/DECISIONS.md` is now a table-of-contents pointing to every ADR in `docs/adr/`. The old inline content lives in 33 new/existing separate files.

### 4. Design doc moved

- `docs/hestia-design-revised-april-2026.md` → `docs/design/hestia-design-revised-april-2026.md`
- Updated relative links in:
  - `docs/design/matrix-integration.md`
  - `docs/roadmap/future-systems-deferred-roadmap.md`
  - `docs/design/hestia-design-revised-april-2026.md` (internal roadmap link)

### 5. Active references updated

| File | Change |
|------|--------|
| `src/hestia/config.py:33` | `ADR-022` → `ADR-0025` |
| `docs/design/hestia-phase-8-plus-roadmap.md` | `ADR-022` → `ADR-0025`, `ADR-023` → `ADR-0023` |
| `docs/guides/email-setup.md:140` | Removed broken link to non-existent `ADR-0016-configuration-and-secrets.md`; now points to L29 handoff |
| `README.md:131` | `ADR-024` → `ADR-0024` |

### 6. Historical records left intact

Loop specs, handoff docs, and `CHANGELOG.md` retain their original ADR references. Rewriting historical records would be revisionist; the index and handoff doc provide the mapping.

---

## Test results

- `pytest tests/docs/ -q`: **1 passed** (link checker)
- `ruff check src/`: **25 errors** (unchanged from baseline; only comment edited in `src/`)

---

## Decisions made

1. **Renumbered DECISIONS.md colliding ADRs** rather than the existing `docs/adr/` files, because the separate files were already linked from recent release docs and handoffs.
2. **ADR-0022 kept for skills preview** (more recent, more references); identity renumbered to **ADR-0025**.
3. **No attempt to rewrite `CHANGELOG.md` or historical handoffs`** — they remain accurate for the point in time they were written.
4. **Removed broken `ADR-0016-configuration-and-secrets.md` link** from `email-setup.md` because that ADR was never actually written.

---

## Carry-forward

- `CHANGELOG.md` line 337 says "ADR-0014 through ADR-0022" — this was accurate at the time of writing (v0.7.11). No action needed unless a future release note wants to reference the full expanded set.
- `docs/development-process/decisions/` directory may now be empty or contain only historical redirect files. Consider removing it in a future cleanup if it's no longer referenced.
