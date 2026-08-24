# L219: Hygiene and VRAM Check Verification

## Goal
Ensure regression fixtures and diagnostics never leak session credentials, and verify the inference server has enough VRAM headroom for three full 131,072-token slots.

## Motivation
The authenticated-browser work (L188) introduced persistent session storage, which means real cookies could end up in regression fixtures or logs if we are not careful. At the same time, the runtime is configured for `-c 393216 -np 3`, so we need evidence that a 12 GB GPU can hold the model plus the full KV cache.

## Scope
- Expand `src/hestia/diagnostics/scrub.py` to redact credential-bearing cookies and high-entropy tokens.
- Add a reusable read-only script (`scripts/verify_vram.py`) that checks live slot config and GPU memory.
- Document the pre-allocation assumption so the projection is honest.

## §1 Scrubber hardening

### Implementation
In `src/hestia/diagnostics/scrub.py`:
- Add `li_at`, `JSESSIONID`, and `indeed_*` cookie names to the inline cookie redaction list.
- Add a high-entropy catch-all that redacts long (32+ char), random-looking token values regardless of the key name.
- Keep existing rules for Telegram tokens, Matrix tokens, emails, IPs, home paths, and API keys.

### Tests
Add tests in `tests/unit/diagnostics/test_scrub.py`:
- LinkedIn cookies (`li_at`, `JSESSIONID`) are redacted.
- Indeed cookies (`indeed_api_token`, `indeed_application_session_id`) are redacted.
- A generic 32+ char alphanumeric token with mixed case and digits is redacted.
- Long lowercase words without digits are left intact.

### Commit
`feat: harden regression fixture scrubber with LinkedIn/Indeed cookies and high-entropy catch-all`

## §2 VRAM check

### Implementation
Add `scripts/verify_vram.py`:
- Query `llama-server` `/slots` to read `n_slots` and `n_ctx` per slot.
- Query `nvidia-smi` for used/total/free VRAM.
- Add a small generation-buffer allowance (512 MiB) to the current used memory.
- Fail if the projected total exceeds 90% of available VRAM.

Add a comment explaining that llama.cpp pre-allocates the KV cache at model load, so the "used" figure already includes the worst-case cache for all configured slots.

### Tests
The script is exercised manually against the live inference server. No unit test is required because it depends on local GPU state, but it returns a non-zero exit code on failure so CI can call it when a GPU is present.

### Commit
`feat: add scripts/verify_vram.py for live VRAM headroom verification`

## §3 Handoff
Update this spec with review carry-forward and write `docs/handoffs/L219-hygiene-and-vram-check-handoff.md`.

## Quality gates
```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Review carry-forward
- The high-entropy catch-all is intentionally aggressive; monitor whether it redacts legitimate long identifiers in fixtures and tune the entropy check if needed.
- `verify_vram.py` is read-only, but a future loop could extend it to perform a safe single-slot load test and measure actual growth.

## Critical rules recap
- Do not merge or push without Dylan's okay.
- No trust/security policy changes.
- No new dependencies.
