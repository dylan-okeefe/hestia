# Kimi loop L33a — `InjectionScanner` threshold tuning + structured-content filters

## Hard step budget

≤ **4 commits**, ≤ **1 new test module**, no exploration outside `src/hestia/security/injection.py`, `src/hestia/config.py` (only the `SecurityConfig` block), and the new test file. Stop after version-bump commit; write `.kimi-done`; push; exit.

## Review carry-forward

From L32c (merged at `<TBD>`):

- Test baseline: **<TBD>**.
- Mypy 0. Ruff ≤ 44.

From the external code-quality review:

- `InjectionScanner.entropy_threshold = 4.2` is too low — real tool outputs (JSON, minified CSS, base64 blobs, technical docs) routinely exceed this. The scanner false-positives constantly, polluting model context with annotations and undermining trust in the signal.
- Need: raise default threshold and skip the entropy gate for content that is clearly structured (still keep the regex pattern check active so known prompt-injection phrases get flagged regardless).

**Branch:** `feature/l33a-injection-scanner-tuning` from `develop` post-L32c.

**Target version:** **0.7.9** (patch — behavior change: scanner is less noisy. Document explicitly in CHANGELOG.).

---

## Scope

### §1 — Raise default `entropy_threshold` and add structured-content filters

In `src/hestia/security/injection.py`:

- Default `entropy_threshold` → **5.5** (from 4.2). Document the empirical baseline ranges in the docstring:
  - English text: ~4.0–4.5
  - JSON: ~5.0–5.5
  - Minified CSS / HTML: ~5.5–6.0
  - Base64 / random bytes: ~6.0+
- Add a `_looks_structured(content: str) -> bool` helper that returns True when content is one of:
  - **JSON** — `json.loads(content.strip())` succeeds (catch `json.JSONDecodeError`).
  - **Base64-only** — length ≥ 100 **and** ≥ 80% of chars match `[A-Za-z0-9+/=]`.
  - **CSS/HTML-ish** — count of `{`/`}`/`;` is dense (≥ 1 per 40 chars) **or** balanced `<...>` tags appear (≥ 3 pairs).
- In the scan flow, when `_looks_structured(content)` is True **and** `SecurityConfig.injection_skip_filters_for_structured` is True, **skip the entropy check** but **still run the regex pattern check**. The regex check catches known prompt-injection phrases (`"ignore previous instructions"`, `"system prompt"`, `"you are now"` etc.) regardless of entropy.

### §2 — Wire `SecurityConfig`

In `src/hestia/config.py` (`SecurityConfig` dataclass):

- Add `injection_entropy_threshold: float = 5.5`.
- Add `injection_skip_filters_for_structured: bool = True`.
- `InjectionScanner` reads both from `SecurityConfig` rather than hardcoding.

### §3 — Tests

`tests/unit/test_injection_scanner_tuning.py`:

- `test_minified_json_no_longer_false_positives` — 1 KB minified JSON ⇒ `scan(...)` returns no annotation (clean). Exercises the JSON branch of `_looks_structured`.
- `test_base64_blob_skipped` — 1 KB pure-base64 string ⇒ no annotation.
- `test_css_block_skipped` — a realistic CSS block (~500 chars, lots of `{`/`}`/`;`) ⇒ no annotation.
- `test_known_injection_phrase_in_json_still_flagged` — JSON containing `"instructions": "ignore previous instructions"` ⇒ flagged. Locks the contract that structured content only skips entropy, not regex.
- `test_threshold_5_5_default_for_english_text` — random English paragraph (200 words) ⇒ no annotation.
- `test_high_entropy_random_bytes_still_flagged_when_not_structured` — 1 KB of uniformly random printable bytes ⇒ flagged (entropy > 5.5, doesn't match any structured filter).
- `test_skip_filters_disabled_via_config` — `injection_skip_filters_for_structured=False` ⇒ JSON entropy is checked; if entropy > threshold, flagged.

### §4 — Version bump + CHANGELOG

- `pyproject.toml` → `0.7.9`.
- `uv lock`.
- CHANGELOG entry under `[0.7.9] — 2026-04-18`. **Explicitly note the behavior change:**
  > **Behavior change:** Default `InjectionScanner.entropy_threshold` raised from 4.2 to 5.5, and structured content (JSON / base64 / CSS) now skips the entropy gate while still running the regex pattern check. This dramatically reduces false-positive annotations on tool outputs. Tunable via `SecurityConfig.injection_entropy_threshold` and `SecurityConfig.injection_skip_filters_for_structured`.
- No new ADR (the L33b/c arc will share an ADR if needed; this single tuning is policy-config sized, not architecture-sized).
- No new handoff doc; the L33-arc handoff lands with L33c.

---

## Commits (4 total)

1. `fix(security): raise entropy threshold to 5.5 and add structured-content filters`
2. `feat(config): expose injection_entropy_threshold and skip-for-structured toggle`
3. `test(security): scanner tuning regression coverage`
4. `chore(release): bump to 0.7.9`

---

## Required commands

```bash
uv lock
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/
```

Mypy 0. Ruff ≤ 44.

---

## `.kimi-done` contract

```
HESTIA_KIMI_DONE=1
LOOP=L33a
BRANCH=feature/l33a-injection-scanner-tuning
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

---

## Critical Rules Recap

- Behavior change is intentional and documented in CHANGELOG.
- Regex pattern check is **never** skipped — only the entropy gate is.
- Push and stop.
