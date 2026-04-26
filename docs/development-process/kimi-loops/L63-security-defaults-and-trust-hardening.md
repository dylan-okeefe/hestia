# L63 — Security Defaults & Trust Hardening

**Status:** Spec ready. Feature branch work — merge to `develop` when green.

**Branch:** `feature/l63-security-defaults-and-trust-hardening` (from `develop`)

## Goal

Fix the four highest-ranked security gaps from the v0.10.x evaluation: permissive filesystem defaults, plaintext password exposure in logs, and zero-friction deployment of the dangerous `developer` trust preset. These are "release gate" items — the kind of defaults that determine whether a new user is safe or accidentally wide-open on first run.

---

## Intent & Meaning

The evaluation identified a pattern: Hestia's defaults assume the operator is an expert who reads every config field. `allowed_roots=["."]` grants filesystem access to whatever directory Hestia happens to start from. `EmailConfig.password` appears in `repr()` output and stack traces. `TrustConfig.developer()` auto-approves every tool including `terminal` with no warning. The **intent** is not merely to change values — it is to shift the project's posture from "expert-only safe" to "safe by default, dangerous only by explicit opt-in." A user who clones Hestia, runs `hestia init`, and starts chatting should not be one misconfigured trust preset away from arbitrary shell execution.

---

## Scope

### §1 — `allowed_roots` default-deny

**File:** `src/hestia/config.py`
**Evaluation:** `allowed_roots = ["."] is a silently permissive default (config.py:98)`. `"."` expands to the CWD at runtime. On a server started from `/` or `/home/user`, this is a full-filesystem write grant via `write_file`. `hestia doctor` warns, but only warns — it does not block.

**Change:**
```python
# Before
allowed_roots: list[str] = field(default_factory=lambda: ["."])

# After
allowed_roots: list[str] = field(default_factory=list)
```

**Intent:** Make the default deny-all. An operator who wants filesystem access must explicitly list roots. The warning in `doctor.py` becomes an error (or at minimum, the tool refuses to operate with an empty allowlist rather than silently failing).

**Commit:** `fix(config): deny-all default for allowed_roots`

---

### §2 — `EmailConfig.password` repr redaction

**File:** `src/hestia/config.py`
**Evaluation:** `password: str = ""` — the resolved_password property correctly prefers `password_env`, but users who set `password` directly store it in a long-lived dataclass that appears in stack traces, memory dumps, and `repr()` output.

**Change:**
- Add `__repr__` to `EmailConfig` that masks `password` and `resolved_password`.
- Consider adding a `repr=False` to the dataclass field, or overriding `__repr__` explicitly.
- Add a deprecation comment/hint toward `password_env`.

**Intent:** A crashed Hestia process or a debug log should never emit a plaintext email password. The redaction makes the safe path (env var) the obvious path.

**Commit:** `fix(config): redact EmailConfig.password in repr`

---

### §3 — `hestia doctor` warns on `developer` trust preset

**File:** `src/hestia/commands/doctor.py`
**Evaluation:** `TrustConfig.developer` has `auto_approve_tools=["*"]` with a comment "development/testing only" but nothing stops production deployment. The README says it's dangerous, but there's no runtime guard.

**Change:**
- Add a check in `doctor.py` that fails (red/X) when `trust.preset == "developer"` AND `HESTIA_ENV` (or equivalent env var) is not `"development"`.
- Message: "Trust preset 'developer' auto-approves all tools. This is not recommended for production. Set HESTIA_ENV=development to acknowledge, or switch to a safer preset."

**Intent:** Make the dangerous preset *noisy*. A user who deploys with `developer()` should see a glaring red check in `hestia doctor` that forces them to acknowledge the risk, not just read a comment.

**Commit:** `feat(doctor): fail check when developer trust preset used outside dev env`

---

### §4 — `TrustConfig.developer` docstring + log warning

**File:** `src/hestia/config.py`
**Evaluation:** The preset is dangerous and has no deterrent beyond a code comment.

**Change:**
- Expand the `developer()` factory method docstring to explicitly list what "*" means (terminal, write_file, etc.).
- Add a runtime `logger.warning()` when `TrustConfig.developer()` is instantiated: "developer trust preset selected — all tools auto-approved."

**Intent:** Defense in depth. Even if `doctor` is skipped, the logs scream the risk at startup.

**Commit:** `fix(config): warn loudly when developer trust preset is selected`

---

## Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Acceptance (Spec-Based)

- `allowed_roots` defaults to `[]`.
- `write_file` / `read_file` refuse to operate when `allowed_roots` is empty (or the tools report a clear error).
- `repr(email_config)` does not contain the literal password string.
- `hestia doctor` exits with a failure indicator when developer preset + non-dev env.
- `TrustConfig.developer()` emits a `logger.warning()` at construction time.

## Acceptance (Intent-Based)

- **A new user who skips reading SECURITY.md is still safe.** Starting Hestia with an empty/default config does not grant filesystem or shell access.
- **A password in a config file does not leak in logs or crashes.** Verify by grepping logs/repr output after a synthetic exception.
- **The developer preset is *frictionful*.** It should feel like a deliberate, acknowledged choice — not a convenient default for "I don't want to think about trust."

## Handoff

- Write `docs/handoffs/L63-security-defaults-and-trust-hardening-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Merge `feature/l63-security-defaults-and-trust-hardening` to `develop`.

## Dependencies

None. Can start immediately from `develop` tip.
