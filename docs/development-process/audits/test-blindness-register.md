# Test-Blindness Register — what passes every gate and is still wrong

**Card:** #45 (Phase 1: audit only) · **Run:** 2026-08-25 · **Branch:** `docs/audit-orphan-triage`
**Method:** targeted verification of six seeded defect classes against
src/ and tests/ at develop b9db06c8. No fixes written, no new tests
written — this is the register Dylan reviews before the fix run.
**Standing rule honored:** every count below states its command.

---

## A. Confirmed instances (class · location · invisibility · detector)

### A1. Class 6 — CI gated a subset of the tree; four directories never ran
- **Location:** `.github/workflows/ci.yml` (pre-L247); `pyproject.toml` testpaths.
- **Invisibility:** the gate itself defined what existed. tests/smoke,
  tests/cli, tests/docs, tests/e2e were collected by no reported command;
  branch counts came from the same subset; reviewers accepted numbers
  without the command (L245 smoke failure is the proven instance).
- **State:** remediation LANDED in L247 — CI now runs whole-tree
  `uv run pytest -q -m "not live"`, `live` marker registered, both
  llama.cpp smoke files marked.
- **Detector still owed (D9):** a collection-coverage meta-test — assert
  `pytest --collect-only -q` yields ≥1 item for every directory under
  tests/ (and that the total matches a recorded floor), so a conftest or
  marker mistake cannot silently empty a directory again.

### A2. Class 2/6 — duplicated calibration-path constant, one depth wrong
- **Location:** `src/hestia/context/builder.py` vs `app.py` (identical
  expression, different nesting; builder's resolved to src/docs/, fixed in
  L247 with a regression test pinning the resolved path).
- **Invisibility:** production serve uses app.py's copy; the wrong copy is
  reachable only off the hot path, and no test imported builder's constant.
- **Detector still owed (D6-family):** a "same-expression-twice" lint is
  overkill; the practical detector is the L247 regression test pattern —
  any module-level path constant gets an exists() assertion. Generalize:
  **every `_DEFAULT_*_PATH` style constant gets an existence-or-explicit-
  fallback test.**

### A3. Class 1 — DECISIONS.md index drifts from docs/adr/
- **Location:** `docs/DECISIONS.md` has 51 `[ADR…]` index rows; `ls
  docs/adr/*.md | wc -l` → 53; grep for ADR-052/ADR-053 in DECISIONS.md →
  0 hits. Both missing ADRs are from this release cycle.
- **Invisibility:** pure documentation, invisible to every gate by design
  today; nobody re-reads the whole index on adding an ADR.
- **Detector (D2):** parse `docs/adr/*.md` filenames; assert each appears
  as a link row in DECISIONS.md, and vice versa (catches dead links too).

### A4. Class 1 — builtin tool definitions vs registration list
- **Location:** 48 `@tool(` declarations under `tools/builtin/`
  (`grep -rc "@tool(" … | sum`); `AppContext.register_tools`
  (`app.py:554+`) registers a hand-maintained sequence of explicit calls
  plus factory tools. Nothing asserts the two sets agree.
- **Invisibility:** a tool exported but never `reg.register`ed imports
  fine, type-checks fine, passes every test that doesn't specifically use
  it, and simply never appears to the model. Its tests (if any) call the
  function directly.
- **Detector (D4):** collect names from `@tool` decorations + factory
  make_* registrations; assert `registry.list_names()` after
  `register_tools()` covers every name on either an inclusion or an
  explicit EXCLUDED_TOOLS list (delegate_task-style conditional tools need
  the escape hatch).

### A5. Class 1/2 — meta-tool identity declared three places
- **Location:** `_META_TOOL_CHAIN_NAMES` set (`execution.py:75`);
  `meta_tool_schemas()` hand-builds three ToolSchemas (`registry.py:285+`);
  dispatch handlers keyed by the same strings in execution.py.
- **Invisibility:** adding/removing a meta-tool requires touching all
  three; miss one and the model sees a schema with no handler, or a
  handler with no schema — both pass all current gates.
- **Detector (D5):** assert `{s.function.name} == _META_TOOL_CHAIN_NAMES ==
  set(dispatch table)`.

### A6. Class 5 — finding-ID comments are documented, not pinned
- **Location/measurement:** `grep -rhoE '(BUG|SEC|PERF)-[0-9]+' src
  --include='*.py' | sort -u | wc -l` → **59** IDs cited in src comments;
  same command over tests/ → **20**; set difference via `comm -23 … | wc
  -l` → **39 IDs referenced in src with no test anywhere citing them.**
  (Correction 2026-08-25: an earlier draft of this register said 40; its
  own stated command produces 39.) Examples: BUG-008 BUG-017
  BUG-036 SEC-006 SEC-007 SEC-014 SEC-015 (full list in run notes).
- **Invisibility:** the comment reads as closure ("BUG-041: excluded from
  aggregates") while the behavior it names may be untested; ruff/mypy/
  pytest never cross-reference prose.
- **Detector (D6):** a meta-test parsing src for finding-ID citations and
  requiring, per ID, ≥1 test file mentioning the same ID OR a line in a
  checked-in waiver file (`docs/audit/FINDING_PIN_WAIVERS.md`) giving the
  reason. Waiver file makes opt-outs visible and reviewable.

### A7. Class 3 — `skills` table exists only in Alembic
- **Location:** `migrations/versions/c3d4e5f6g7h8_add_skills_table.py`;
  no `skills` sa.Table in `persistence/schema.py` and no reader in src
  (`grep -rn skills src/hestia --include=*.py` → 0 hits).
- **Invisibility:** production bootstrap is create_all + runtime
  migrations, which never runs Alembic — the table silently does not exist
  on any real deployment. Today nothing reads it, so nothing crashes: the
  defect is a landmine, not a fire. (Contrast error_resolutions, which HAD
  the Alembic-only shape, fired, and was fixed into schema.py.)
- **Detector (D8, narrow form):** assert every CREATE TABLE across
  migrations/versions also exists in the metadata create_all builds (or is
  explicitly listed as alembic-only-historical). The full bidirectional
  schema-equivalence detector belongs to #46.

### A8. Class 1 — frontend node palette duplicates NODE_TYPES
- **Location:** `web-ui/src/components/workflow-editor/constants.ts:11-16`
  lists node types by hand; backend truth is `NODE_TYPES`
  (`workflows/nodes/__init__.py`). L245 added the backend-side
  classification detector; nothing pins the frontend list to it.
- **Invisibility:** adding a backend node type without updating the
  palette passes every Python gate; the type is creatable via API but
  invisible to editors (or vice versa if palette leads).
- **Detector (D7):** emit NODE_TYPES keys via a tiny management endpoint
  or generated JSON fixture committed to the repo; vitest asserts palette
  parity. Cross-language, hence fixture-based.

### A9. Class 6 residue — reported counts still lack their commands
- **Location:** process convention, not code. Standing rule established
  2026-08-24 after the L245 smoke incident.
- **Detector (D1):** `scripts/gate` wrapper that runs ruff/mypy/pytest,
  then prints `<command> → <counts>` as its final artifact line, and writes
  the same to a file the handoff must reference. Cheap; converts the
  standing rule from discipline into artifact. This register is itself the
  argument for it: A6 stated a count (40), gave the command, and the
  command produced 39 — caught only because the number was checkable.

## B. Resolved exemplars (kept as class evidence)

- **Class 2 exemplar closed:** capability-gate reimplementing
  InvestigateNode._resolve — replaced by shared `resolve_invoked_tools`
  (L245 chunk B); both sides now import one source.
- **Class 4 exemplar closed:** executor `if gate is None: return` fail-open
  — registry now refuses unbound gates in both modes (round-2 P4) and the
  invariant lives as a comment where the next editor will read it.
- **Class 6 exemplar closed:** CI subset — see A1.
- **Class 2 live instance remaining:** calibration constant duplication
  (A2) — fix landed, dedup deliberately deferred (import cycle), regression
  test landed.

## C. Suspected, unconfirmed (no located instance — do not pad upward)

- Event-bus subscriber registration drift (define handler vs subscribe)
  — no second subscription site found yet; needs one deliberate search.
- `_STARTER_CONFIG` in admin.py drifting from deploy/example_config.* and
  current HestiaConfig fields (config.py gains fields; starter configs age).
- Capability labels vs `_DESTRUCTIVE_CAPABILITIES`/`_DESTRUCTIVE_TOOL_NAMES`
  overlap drift — destructive-by-name tools whose label says otherwise.
- UPGRADE.md supported-version mentions going stale after each release
  (same species as the SECURITY.md table fixed in #52).
- `config.runtime.example.py` field coverage vs `HestiaConfig` fields.

## D. Mutation testing status

NOT STARTED, per the card's hard gate: the register and detector list are
complete but the run budget remaining is well under two hours. Recommend a
scoped `mutmut` pass (orchestrator/, policy/, persistence/) as a standalone
one-off measurement; surviving mutants land here as pre-proven instances.

## E. Detector priority order (for the reviewed fix run)

1. **D1** gate artifact script (enforces the standing rule mechanically).
2. **D6** finding-ID pinning meta-test + waiver file (closes class 5 at
   scale — 40 unpinned IDs today).
3. **D9** collection-coverage assertion (makes A1-class regressions impossible).
4. **D2** ADR/index sync.
5. **D4** tool registration completeness.
6. **D5** meta-tool triple-consistency.
7. **D7** frontend node-palette parity (needs the JSON fixture decision).
8. **D8** alembic-only table detector (skills; full equivalence stays with #46).


## Addendum 2026-08-25 — THE TRANSPORTED COUNT (variant of A9)

Instance: ORPHAN_TRIAGE.md's header stated a tally ("6 FIXED / 33 STILL
OPEN / 2 / 1") that was true when the reviewer dictated it and false the
moment the reviewer's own next instruction (reclassify BUG-062 out of
FIXED) was applied. The implementing run transcribed the dictation,
labelled it "recomputed from the table", and shipped both. Caught by the
reviewer re-running the count against the committed file.

Why A9/D1 does not cover it: D1 pins TEST counts to their command. This
was a prose count over a checked-in table — no test, no command at write
time, nothing executable to pin.

Detector (new, D10): any stated tally over a checked-in table must be
GENERATED — a script (or test) recomputes the bucket counts from the file
and compares them to the header; the header carries the command, not a
transcription. Landed practice as of 2026-08-25: ORPHAN_TRIAGE.md's header
is pasted from `grep -oE … | sort | uniq -c` output.

This is the third occurrence in three days (L245 reported count without
command; this register's 40-vs-39; this transported tally), twice caused
by the reviewer. The class has its own name now.

## Addendum 2026-08-26 — CONFIRMED CLASS: comparison bound in the wrong type (BUG-067 family)

A DateTime column compared against a `.isoformat()` STRING does not raise;
SQLite compares TEXT lexicographically, and 'T' (isoformat separator) sorts
above the driver's space-separated datetime rendering, so every same-day
row silently mismatches. mypy is satisfied; the only observable symptom is
a wrong result set. No gate sees it.

Confirmed instances (both fixed red-green on fix/sec-010-memory-scope):
- `reflection/scheduler.py` `_is_idle` — reflection could fire while the
  user was actively chatting.
- `style/scheduler.py` `_is_idle` — byte-identical copy, found only because
  review round 3 demanded checking the sibling before assuming clean.

Suspected and CLEARED by writer/cutoff format analysis:
- `memory/store.py` list_inactive_memories retention window — deleted_at
  writer and cutoff are both isoformat strings; consistent.
- `maintenance_trace_store.py` clear_old — created_at writer and cutoff
  both isoformat strings; consistent.

Detector candidate (D11), wording corrected 2026-08-26 per #58 round-4
review: the defect is NOT "isoformat in a comparison" - isoformat-written
AND isoformat-read is consistent (both cleared suspects prove it). The
defect is A READ FORMAT THAT DISAGREES WITH THE WRITE FORMAT for the same
column. D11 therefore flags any comparison parameter whose binding format
differs from how that column's rows are written - today that means
`.isoformat()` strings bound against columns written via datetime-object
binding. Grep-level over sa.text/sa.select comparisons; cheap; would have
caught both scheduler sites.

## Addendum 2026-09-04 — two entries from card #60 (observability)

### B1. CONFIRMED CLASS: detector matched the token the code can see, not the thing the rule is about

Card #60's prompt-drift detector (serve.py `_missing_system_prompt_rules`,
landed 2026-09-03) compared default vs runtime `system_prompt` rules by
their NUMBERS. The incident it was written for — three and a half months
of Hestia not choosing to remember — had every number 1..N still present:
rule 6 (USER CORRECTIONS & PREFERENCES) was buried at position 15 among
browser/search rules and rule 7 (MEMORY SCOPE) was absent. Number-matching
returned `{}` against exactly that shape. A unit test
(`test_reordered_rules_are_not_missing`) froze the blind spot as intended
behaviour.

Fixed 2026-09-04 on feat/60-observability-onto-develop: match the rule's
uppercase HEADING before the colon, not its position; demonstrated red
against a reconstruction of the pre-fix runtime prompt (old logic → `{}`,
new logic → names MEMORY SCOPE). Same shape as the register's standing
lesson: the first version of a detector tends to match what the code can
see (positions, tokens) rather than what the rule is about (identity,
semantics) — and a test written to the first version cements it.

Generalize: **any detector that compares two artifacts must key on
content identity, not on positional/index artifacts of the representation.**

### B2. CONFIRMED CLASS: health metric whose null value is ambiguous

Card #60 spent a week treating `proposals=0` as evidence of breakage.
The count was CORRECT: reflection ticks fired, inference calls landed,
the idle guard passed — there was simply near-zero conversation traffic,
so the pattern miners (frustration, correction, slow_turn, repeated_chain,
tool_failure) found nothing. Zero under near-zero usage is correct
behaviour; zero under normal usage would be a fault. The number alone
cannot distinguish the two, and the startup health surface (also #60)
now reports it every boot — a value that still needs interpreting.

The Sep 1 Telegram session is the exemplar: a twenty-turn conversation
titled "Get to know me", all traces successful, no tools called, no
memories saved. Someone explicitly invited Hestia to learn about them and
it learned nothing — visible only by cross-reading traces and the memory
table, not from any count.

Generalize: **a health metric whose null value is ambiguous needs its
traffic/denominator reported alongside it** (here: session/trace counts in
the same health line), or the null will keep being read as a fault.
