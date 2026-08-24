# Maintainability & Technical Debt Audit — Hestia

**Audit date:** 2026-08-22 · Scope: duplication, dead/obsolete code, problematic abstractions, consistency, dependencies, developer experience.
Evidence sources: direct file inspection, git churn analysis (2026-01-01→HEAD), live worktree observation.

---

## 1. Churn hotspots (git, files touched since Jan 2026)

config.py **93** · orchestrator/engine.py **92** · cli.py **89** · app.py **88** · orchestrator/execution.py **67** · telegram_adapter.py **49** · web-ui/api/client.ts **47** · tools/builtin/__init__.py **39** · context/builder.py **39**.

Interpretation: churn concentrates on composition/policy surfaces (config, engine, app) and the two biggest modules (execution.py 1,738 LOC; telegram_adapter.py 1,246 LOC). These are exactly where this audit found the highest defect density (lock race, gate bypass adjacency, voice-path skips) — high churn + giant modules + convention-based safety = the debt profile.

## 2. Dead & obsolete code (delete list)

| Item | Evidence | Note |
|------|----------|------|
| `session_handoffs` table | declared `schema.py:218-230`, created by m002, **zero readers/writers in src** (`handoff_service.py` documents it doesn't use it); live DB holds 46 legacy rows | dead schema + stale data |
| `get_turn_messages` ×2 | `turn_store.py:213-229`, `message_store.py:186-207`; zero callers; wrong join semantics | delete both |
| `CliPlatform` | used only by its own tests; real REPL bypasses it (`cli_adapter.py:20-21`) | decide: adopt or delete |
| Telegram config fields never read | `fallback_ips`, `connect_timeout_seconds`, `read_timeout_seconds` (`config.py:157-164`); adapter hardcodes HTTP/1.1 instead of reading `http_version` | remove or wire |
| `ConfirmationRequest.request_token` | stored for "audit correlation", never read downstream | wire into audit or drop |
| `validate_matrix_room_alias` | `allowlist.py:87-96`, no callers anywhere incl. tests | delete |
| `Platform.delete_message` (+ Matrix override) | zero callers in src | delete |
| `_BLOCKED_RANGES` module constant | `http_get.py:35-46`, never referenced (transport has its own list) — implies dual coverage that doesn't exist | delete (misleading) |
| `ssrf.is_ssrf_blocked` | no callers | delete or use |
| Deprecated aliases | `CoreAppContext`/`FeatureAppContext`/`CliAppContext` (`app.py:624-627`) | announce removal date |
| FE dead API surface | `saveConfig` (Config page read-only), global `fetchMemories`, `deferProposal` never imported — **the Defer feature is missing from UI despite backend support** | implement Defer button or delete client fn |
| `Database.execute()` wrapper | unused | delete |
| `EventBus.publish_nowait` sync fallback | latent destroyer of handler tasks (`bus.py:66-68`) | remove fallback |
| `escape_room_planning.md` | tracked at repo root; unrelated personal planning note | move out of repo per release-discipline privacy rules |

## 3. Duplication (each instance already produced divergence or bugs)

1. **Dynamic WHERE-builder ×4** (`trace_store.py:116-137`, `failure_store.py:116-137`, `maintenance_trace_store.py:93-113`, capability_events.list_since) — the two carrying the IN-clause feature are the two broken with the identical bug. A shared helper fixes one bug four times over.
2. **Edit rate-limiting ×2 adapters**, divergent pruning: Telegram evicts (`telegram_adapter.py:359-364`), Matrix grows unbounded (`matrix_adapter.py:64`).
3. **Reset flows ×2**, divergent semantics: TG pays LLM summary + carries context forward; MX plants fixed marker + clean start.
4. **Scheduler callback factories ×3**: `make_serve_scheduler_callback` supersedes TG/MX variants; all three live (`runners.py:88-140`).
5. **Allowlist guard block copy-pasted into seven Telegram handlers** (`telegram_adapter.py:665,683,730,776,800,826,852`) vs centralized Matrix dispatch.
6. **Two persistence write idioms**: ORM-typed inserts (session/turn/message/scheduler stores) vs pre-formatted `sa.text()` strings (trace/failure/capability/users/maintenance/error stores) — root cause of the binding crash class and PG timestamp incompatibilities.
7. **Row-mapping datetime patching ×6 stores**; scheduler's `_ensure_utc` is the correct shared helper candidate.
8. **HandoffService instantiated twice** — `app.py:244` eager instance ignored by `make_orchestrator` which builds another (`app.py:477-480`).
9. **FE date formatting ×5 styles** (toLocaleString raw ×5 sites, reimplemented relative time vs shared helper, raw ISO once).
10. **FE destructive confirms ×2 patterns** (native window.confirm ×7 call sites vs styled ConfirmDialog ×3).
11. **Policy docs duplicated**: `.cursorrules` (270 lines) vs `AGENTS.md` (54 lines), both tracked, overlapping governance that has already drifted apart.

## 4. Problematic abstractions

| Abstraction | Problem | Direction |
|-------------|---------|-----------|
| Gate-by-convention (ARCH-001) | Safety depends on each new call site remembering to consult the gate; 4 bypasses prove the failure mode | Registry-level chokepoint (see roadmap #1) |
| NODE_TYPES registry vs executor fallback | Two dispatch paths with different security semantics in the same function (`executor.py:366-378` vs `:412-434`) — the seam SEC-001 lives in | One path; nodes receive an execution context that includes authorization |
| `_resolve` inputs-over-config precedence (workflows) | Trigger payloads silently override author-pinned node config — surprising and exploitable (SEC-022) | Config wins; inputs only fill gaps |
| Module-global web context singleton (`set_web_context`) | Hidden coupling; test contamination risk | App-scoped dependency injection via FastAPI Depends |
| Monkey-patched `inference.close = _noop_close` (`serve.py:34`) | Method-assign lifecycle hack; fragile ordering | Explicit ownership parameter ("don't close") on runners |
| Config-as-Python-file across dual worktrees (ADR-028) | Runtime vs dev divergence invisible to git; personal values must be kept out of origin by discipline alone | Env-layer covers most needs; consider shrinking runtime-only delta |
| Status vocabularies | Workflows know only ok/failed while turns have rich journaled states — workflows can't express what's happening | Borrow the turn-state pattern |

## 5. Consistency inventory (naming/terminology)

- Dashboard IA names drift from domain names: "Knowledge"=memories, "Error Log"=failure bundles+resolutions, "Profile" vs "Style Profile" overlap, "Browser Sessions" vs chat sessions ambiguity.
- Channel classification fallbacks default to CLI (`execution.py:1512`) — misattributes voice turns today, any future surface tomorrow.
- Interpolation dialects: `${n.id}.output` upstream refs vs `{{data.X}}` trigger payload — two syntaxes one editor.
- Command parsing: exact-token (Telegram PTB) vs prefix-match (Matrix hand-rolled).
- Error delivery: some errors double-delivered (rate limit), others silent (interpolation) — no single convention.

## 6. Dependency observations

Backend deps are lean and justified (checked pyproject: fastapi, sqlalchemy, PTB, matrix-nio, httpx, curl_cffi optional, playwright optional, croniter, click…). Frontend: `@openuidev/react-ui` is pure overhead (theme scaffolding only) — biggest drop candidate; React Flow is heavy but core to the editor (chunk-split instead of removal); cronstrue imported core-only (good). Root-level stray `node_modules/` (gitignored) suggests a past misplaced install — harmless but confusing.

## 7. Developer-experience assessment

**Good:** uv workflow documented; quality-gate commands canonical in AGENTS.md; loop-spec/handoff conventions consistent; docs-as-tests keep README honest; deploy/ examples cover the real topologies; metrics refresh scripted.

**Friction:**
1. **Red gates + broken build normalize "passing locally"** — the single biggest DX hazard (TEST-001).
2. **No whole-app dev mode**: `--reload` watches only uvicorn; platform adapters/scheduler run stale code, so every change requires full service restart (documented in skill but still heavy iteration cost). A `--dev` profile running everything under a supervisor-aware reloader would pay for itself quickly.
3. **Current-state discoverability leans on external board** (TaskView); in-repo, `docs/development-process/` is archaeology-rich but "what's true right now" requires cross-referencing KIMI_CURRENT + progress trackers.
4. **Calibration/model coupling silent**: swapping models mis-budgets tokens without warning (PERF-015).
5. **Duplicate policy surfaces** (.cursorrules vs AGENTS.md) mean agent-behavior edits must land twice or drift.
6. **Test feedback is good** (~260 s deterministic) — preserve by keeping the suite red-flag-free.

## 8. Debt items that are *fine* (explicitly not recommending action)

- Alembic retained as reference-only despite staleness: acceptable *if* README says loudly which tables were never covered (currently only FTS5 exception documented) — either regenerate a snapshot baseline revision or document, don't leave ambiguous.
- execution.py size: the state machine reads clearly; splitting before the gate-chokepoint refactor would add merge pain. Split after, along assembly/execution/finalization seams that already exist conceptually.
- Python-file config overall: works for operator-developer; revisit only if multi-operator ever matters.

## 9. Priority deletions/simplifications (quick wins)

1. Delete-list §2 (≈1 day total, shrinks cognitive load and removes misleading constants like `_BLOCKED_RANGES`).
2. Shared WHERE-builder + timestamp normalizer in persistence (kills a bug class).
3. Consolidate .cursorrules → AGENTS.md (single source of agent policy).
4. Implement-or-delete `deferProposal` (a whole feature is stranded behind a missing button).
5. Single HandoffService instance.
