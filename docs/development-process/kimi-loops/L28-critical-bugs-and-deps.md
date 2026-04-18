# Kimi loop L28 — critical correctness bugs + dependency hygiene

## Review carry-forward

From **two external reviewers** (capability-audit follow-up + public-release evaluation, both 2026-04-18). All claims verified by Cursor against `develop` tip `e2d64a0`:

- **`bleach` is imported but missing from `pyproject.toml` and `uv.lock`** — `src/hestia/email/adapter.py:18` imports `bleach`, but it is not in `dependencies`. Default `EmailConfig.sanitize_html=True` ⇒ `ModuleNotFoundError` at first IMAP read for **any** new user with HTML mail. Bonus: `bleach` was archived/unmaintained in 2023; replace with **`nh3`** (Rust-backed, maintained, drop-in for `bleach.clean(..., tags=[], strip=True)`).
- **`read_artifact` tool is never registered in CLI** — `make_read_artifact_tool` exists and is exported from `hestia.tools.builtin.__init__`, but `cli.py` only registers `search_memory`, `save_memory`, `list_memories`. README claims `read_artifact` is a core feature. Model says "I stored that as artifact://…" then has no tool to fetch it back.
- **`email_draft` always falls back to `"draft-unknown"`** — `src/hestia/email/adapter.py:345` reads `msg["Message-ID"]` immediately after `EmailMessage()` construction. Python's `email.message.EmailMessage` does **not** auto-assign a Message-ID; the value is `None`, the subsequent `HEADER Message-ID "None"` IMAP search returns nothing, and the fallback `return "draft-unknown"` (line 354) ships a sentinel that downstream `send_draft` accepts as a real UID.
- **IMAP injection in `_parse_search_query`** — `src/hestia/email/adapter.py:288,290,296,301` interpolate raw user/model input into IMAP `SEARCH` quoted strings with no escaping. A model-controlled query like `FROM:alice" OR ALL HEADER X "` escapes the quoted string and injects arbitrary criteria. Web-content-fed memory searches make this exploitable in practice.
- **Silent malformed-date fallthrough in `_parse_search_query`** — `src/hestia/email/adapter.py:297-298`: a bad `SINCE:` token (e.g. `SINCE:2026-99-99`) falls through to a subject-text search of the literal token instead of raising. Surprising; mask the underlying user error.
- **Dead `StyleProfileBuilder.get_profile_dict()` stub** — `src/hestia/style/builder.py:234` is a synchronous method that **returns `{}`**. The orchestrator awaits the **async** `StyleStore.get_profile_dict()` (the real implementation). The builder method is dead, will trip anyone who autocompletes off the wrong object, and will silently disable style prefixes if accidentally wired.
- **`draft-unknown` UID** — even after the Message-ID fix, the placeholder return path is wrong: any UID-lookup miss should raise `EmailAdapterError` so callers cannot accept a sentinel as a valid handle.
- Lockfile hygiene: keep `uv.lock` in sync with the **same** commit as any version bump (re-learnt twice in L24 and L26).
- Test gate: `uv run pytest tests/unit/ tests/integration/` and `uv run mypy src/hestia` both **must** stay at 0 failures / 0 mypy errors.

**Branch:** `feature/l28-critical-bugs` from **`develop`**.

**Target version:** **0.7.2** (patch — bug fixes only, zero breaking surface).

---

## Goal

Fix the seven correctness bugs above with regression tests for each, and harden the email adapter's quote handling. **No refactors. No new features.** Anything architectural belongs in L30–L33.

---

## Scope

### §-1 — Merge prep

- Fast-forward `develop` from origin.
- Branch `feature/l28-critical-bugs` from `develop` tip.
- Confirm `git status` clean.

### §0 — Cleanup carry-forward

None — this loop **is** the cleanup loop.

### §1 — Replace `bleach` with `nh3`

**Why nh3:** `bleach` was archived in 2023; `nh3` is the actively-maintained successor (Rust-backed via `ammonia`). Same use case (strip-all-tags HTML cleaning). API:

```python
import nh3
cleaned = nh3.clean(raw_html, tags=set())  # strip every tag, keep text
```

Equivalent to the current `bleach.clean(raw_html, tags=[], strip=True)`.

**Changes:**

- `pyproject.toml` `dependencies`: add `"nh3>=0.2.17"`. Remove any `bleach` reference (there is none).
- `src/hestia/email/adapter.py`: replace `import bleach  # type: ignore[import-untyped]` with `import nh3`. Replace `bleach.clean(raw_html, tags=[], strip=True)` with `nh3.clean(raw_html, tags=set())`. Drop the `# type: ignore` (nh3 ships type stubs).
- `uv lock` to refresh `uv.lock`. Commit lockfile in the same commit.

**Tests:**

- `tests/unit/test_email_adapter_html_sanitize.py` — new file (or extend existing email adapter unit tests):
  - `test_sanitize_strips_script_tag` — input `<p>hi</p><script>alert(1)</script>`, expect `hi` (no `script`).
  - `test_sanitize_disabled_passthrough` — `sanitize_html=False` returns input verbatim.
  - `test_sanitize_handles_empty_string` — empty input returns empty string (no crash).
- Run `uv run pytest tests/unit/test_email_adapter*` to confirm green.

**Commit:** `fix(email): replace archived bleach with nh3 for HTML sanitization`

### §2 — Register `read_artifact` and add `delete_memory`

#### §2a — Register `read_artifact`

In `src/hestia/cli.py`, the same block that registers memory tools (around line 386) must register `read_artifact`. The `ArtifactStore` already exists on `CliAppContext` (verify with `rg -n "ArtifactStore" src/hestia/cli.py`). Add:

```python
from hestia.tools.builtin import make_read_artifact_tool
...
tool_registry.register(make_read_artifact_tool(artifact_store))
```

Wire `artifact_store` through `CliAppContext` if it is not already exposed.

#### §2b — Add `delete_memory` tool

New file `src/hestia/tools/builtin/memory_tools.py` already contains `make_search_memory_tool`, `make_save_memory_tool`, `make_list_memories_tool`. Append:

```python
def make_delete_memory_tool(store: MemoryStore) -> Tool:
    """Tool: delete a memory record by id. Requires confirmation by default."""
    @tool(
        name="delete_memory",
        description="Delete a memory record by its id. Use list_memories to find ids.",
        capabilities=[Capability.MEMORY_WRITE],
        requires_confirmation=True,
    )
    async def delete_memory(memory_id: str) -> str:
        deleted = await store.delete(memory_id)
        if not deleted:
            return f"No memory with id {memory_id}"
        return f"Deleted memory {memory_id}"
    return delete_memory
```

Match exact signatures used by sibling tools (look at `make_save_memory_tool` for the canonical shape; mirror its decorator order and capability list semantics). Export from `hestia/tools/builtin/__init__.py`.

Register in `cli.py` next to the other memory tool registrations.

**Tests:**

- `tests/unit/test_read_artifact_registered.py` — new test that builds `CliAppContext` via the bootstrap path used in existing tests and asserts `tool_registry.get("read_artifact")` does not raise. Same shape for `delete_memory`.
- `tests/unit/test_delete_memory_tool.py` — exercise `make_delete_memory_tool` against an in-memory `MemoryStore` (use the same fixture other memory tool tests use): save → delete by id → list → assert empty; delete unknown id → friendly message.
- Smoke: `tests/integration/test_cli_tools_registered.py` — invoke `hestia tools list` (or whatever the CLI command is — check existing tests) and assert both new tools appear.

**Commit:** `feat(tools): register read_artifact and add delete_memory in CLI`

### §3 — Fix `email_draft` Message-ID and remove `draft-unknown` sentinel

In `src/hestia/email/adapter.py::create_draft`:

1. **Generate the Message-ID before append**:

   ```python
   import email.utils
   ...
   if "Message-ID" not in msg:
       msg["Message-ID"] = email.utils.make_msgid(domain=self.config.username.split("@")[-1])
   ```

   Place this **before** `raw = msg.as_bytes()` so the bytes include the header.

2. **Quote the Message-ID for IMAP search** — Message-IDs contain `<` and `>`, which are fine inside IMAP quoted strings, but no other escaping is required. Keep the existing search shape but base it on the just-assigned `mid` (which is now guaranteed non-`None`).

3. **Replace the `return "draft-unknown"` fallback** with:

   ```python
   raise EmailAdapterError(
       f"Created draft but could not locate it in Drafts by Message-ID {mid!r}"
   )
   ```

4. **`send_draft`** unchanged behaviorally, but add an explicit guard at the top: `if draft_id == "draft-unknown": raise EmailAdapterError("...")` to surface the bug if any caller still passes a stale value.

**Tests:**

- `tests/unit/test_email_create_draft.py` — extend existing email tests (or new file) using a mock IMAP connection that captures `append`/`uid("SEARCH", ...)` arguments:
  - `test_create_draft_assigns_message_id` — assert the appended bytes contain a `Message-ID:` header.
  - `test_create_draft_returns_real_uid_when_search_succeeds` — mock returns `("OK", [b"42"])` ⇒ method returns `"42"`.
  - `test_create_draft_raises_when_search_misses` — mock returns `("OK", [b""])` ⇒ `EmailAdapterError`. **Must not return `"draft-unknown"`.**
  - `test_send_draft_rejects_draft_unknown` — direct call with `"draft-unknown"` raises.

**Commit:** `fix(email): generate Message-ID and raise on missing draft UID`

### §4 — Harden `_parse_search_query` (IMAP injection + malformed dates)

Replace `src/hestia/email/adapter.py::_parse_search_query` with a hardened version:

1. **Quote escaping** — IMAP quoted strings escape `\` → `\\` and `"` → `\"`. Add a helper:

   ```python
   @staticmethod
   def _imap_quote(value: str) -> str:
       return value.replace("\\", "\\\\").replace('"', '\\"')
   ```

   Apply to **every** interpolated token: `f'FROM "{self._imap_quote(token[5:])}"'`, etc.

2. **Strict date parsing** — when `SINCE:` parsing fails, raise `EmailAdapterError(f"Invalid SINCE date: {date_str!r}; expected YYYY-MM-DD")`. **Do not** fall through to a subject search. Bubble the error up to the tool dispatcher (the tool returns it as an `error` `ToolCallResult`).

3. Document the supported grammar in the docstring (`FROM:`, `SUBJECT:`, `SINCE:`, default ⇒ subject text).

**Tests:**

- `tests/unit/test_email_search_parser.py` — new file:
  - `test_basic_from` — `FROM:alice@example.com` → `'(FROM "alice@example.com")'`.
  - `test_basic_subject` — `SUBJECT:hello` → `'(SUBJECT "hello")'`.
  - `test_basic_since` — `SINCE:2026-04-18` → `'(SINCE "18-Apr-2026")'`.
  - `test_quote_escaping` — input containing `"` is escaped (`\"`).
  - `test_imap_injection_attempt` — input `FROM:alice" OR ALL HEADER X "` produces a single FROM clause with the literal value escaped; **no** stray `OR ALL` in output.
  - `test_malformed_since_raises` — `SINCE:2026-99-99` raises `EmailAdapterError`.
  - `test_default_subject_search` — bare token → `(SUBJECT "...")`.

**Commit:** `fix(email): escape IMAP quotes and reject malformed SINCE dates`

### §5 — Delete dead `StyleProfileBuilder.get_profile_dict`

Remove `src/hestia/style/builder.py::get_profile_dict` (lines ~234–243). The real implementation lives on `StyleStore.get_profile_dict` (async) and the orchestrator already awaits the store version. Confirm no caller imports the builder version with `rg -n "builder\.get_profile_dict|StyleProfileBuilder.*\.get_profile_dict" -- src tests`.

**Tests:**

- `tests/unit/test_style_builder_no_dead_method.py` — assert `not hasattr(StyleProfileBuilder, "get_profile_dict")`. This fails fast if anyone re-adds the stub.
- Re-run `tests/unit/test_style_builder.py` and `tests/unit/test_style_profile_context.py` to confirm green.

**Commit:** `refactor(style): drop dead StyleProfileBuilder.get_profile_dict stub`

### §6 — Version bump + lockfile + CHANGELOG

- `pyproject.toml` `version = "0.7.2"`.
- `uv lock` again to capture the bump (combine with §1 lockfile if landing same commit, otherwise standalone).
- `CHANGELOG.md` — new section under `## [0.7.2] — 2026-04-18`:
  - Replace `bleach` with `nh3` (security/dependency hygiene).
  - Register `read_artifact`; add `delete_memory` tool.
  - Fix email draft Message-ID generation; remove `draft-unknown` sentinel.
  - Escape IMAP quotes in search queries; reject malformed `SINCE:` dates.
  - Drop dead `StyleProfileBuilder.get_profile_dict` stub.

**Commit:** `chore(release): bump to 0.7.2`

### §7 — Handoff report

`docs/handoffs/L28-critical-bugs-handoff.md` (mirror prior handoff template):

- Section table (file, commit, what shipped).
- Test counts before/after.
- Mypy counts before/after.
- Blockers / deferred (should be `none`).
- Post-loop checklist.

**Commit:** `docs(handoff): L28 critical bugs report`

---

## Required commands

```bash
uv lock                                            # after dep changes
uv run pytest tests/unit/ tests/integration/ -q    # must be green
uv run mypy src/hestia                             # must be 0 errors
uv run ruff check src/hestia tests                 # baseline
```

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

Write `./.kimi-done` at the end with:

```
HESTIA_KIMI_DONE=1
LOOP=L28
BRANCH=feature/l28-critical-bugs
COMMIT=<final commit sha>
TESTS=passed=N failed=0 skipped=M
MYPY_FINAL_ERRORS=0
```

If blocked, set `HESTIA_KIMI_DONE=0` and add `BLOCKER=<reason>`.

---

## Critical Rules Recap

- One commit per logical section.
- Conventional commits (`fix:`, `feat:`, `refactor:`, `chore:`, `docs:`).
- **Do not merge to `develop`.** Push the feature branch and stop after `.kimi-done`.
- **No refactors beyond what each fix requires.** L30–L33 own architecture.
- Every bug fix needs at least one regression test that **would have caught the bug** before this loop.
