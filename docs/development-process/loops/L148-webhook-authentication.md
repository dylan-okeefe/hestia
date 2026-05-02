# L148 — Webhook Authentication

**Status:** Spec only
**Branch:** `feature/l148-webhook-authentication` (from `feature/workflow-builder`)
**Depends on:** L134

## Intent

`POST /api/webhooks/{endpoint}` accepts arbitrary requests with no authentication. Any process on localhost (or the network if bound to 0.0.0.0) can trigger arbitrary workflow executions by guessing or enumerating endpoint names. The webhook route explicitly bypasses session auth (the test verifies this), so there is currently zero access control on workflow triggering via webhook.

## Scope

### §1 — Per-workflow webhook secret in trigger config

In `src/hestia/workflows/models.py`:

1. No schema change needed — `trigger_config` is already `dict[str, Any]`. Document the convention: when `trigger_type == "webhook"`, `trigger_config` should contain `{"endpoint": "...", "secret": "..."}`.

In `src/hestia/web/routes/workflows.py`, in the `create_workflow` endpoint:

2. When `trigger_type == "webhook"` and no `secret` is provided in `trigger_config`, auto-generate one using `secrets.token_urlsafe(32)` and include it in the stored config and the response. This ensures every webhook workflow has a secret from creation.

**Commit:** `feat(workflows): auto-generate webhook secret on workflow creation`

### §2 — HMAC signature validation on webhook endpoint

In `src/hestia/web/routes/workflows.py`, modify `receive_webhook`:

1. After receiving the request body, look up all workflows with `trigger_type == "webhook"` and `trigger_config.endpoint == endpoint` (query the store, or use the trigger registry's workflow list).
2. If no matching workflow exists, return 404 `{"detail": "Unknown webhook endpoint"}` (don't reveal whether the endpoint exists via timing — but for a local-first app this is acceptable).
3. Extract `X-Webhook-Signature` header from the request.
4. For the matched workflow, compute `hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()`.
5. Compare using `hmac.compare_digest(computed, provided_signature)`.
6. If missing header: return 401 `{"detail": "Missing X-Webhook-Signature header"}`.
7. If mismatch: return 401 `{"detail": "Invalid webhook signature"}`.
8. If valid: proceed with publishing the event as before.

**Commit:** `feat(workflows): HMAC-SHA256 webhook signature validation`

### §3 — Expose webhook URL and secret in API response

In `src/hestia/web/routes/workflows.py`:

1. In the workflow detail response (`GET /workflows/{id}`), when `trigger_type == "webhook"`, include a computed `webhook_url` field: `f"http://{config.web.host}:{config.web.port}/api/webhooks/{endpoint}"`.
2. Include the `secret` in the response so the UI can display it for the user to configure in their external service.

In the frontend:

3. In the trigger config panel of `WorkflowEditor.tsx`, when `trigger_type == "webhook"`, display the webhook URL and secret as read-only copyable fields. Show a small help text: "Configure your external service to POST to this URL with header `X-Webhook-Signature: hmac_sha256(secret, body)`".

**Commit:** `feat(web-ui): display webhook URL and secret in trigger config panel`

### §4 — Tests

1. **Webhook auth success test:** Create a workflow with webhook trigger + secret. Send request with valid HMAC signature. Assert 202 and event published.
2. **Webhook auth missing header:** Send request without `X-Webhook-Signature`. Assert 401.
3. **Webhook auth invalid signature:** Send request with wrong signature. Assert 401.
4. **Webhook auth timing-safe:** Assert `hmac.compare_digest` is used (mock and verify, or inspect the implementation).
5. **Auto-generation test:** Create a webhook workflow without providing a secret. Assert the response contains a generated `secret` in `trigger_config`.
6. **Unknown endpoint test:** Send to an endpoint that no workflow uses. Assert 404.

**Commit:** `test(workflows): webhook HMAC authentication tests`

## Evaluation

- Webhook endpoint rejects requests without valid HMAC signature
- Webhook secret is auto-generated on workflow creation if not provided
- UI displays the webhook URL and secret for user to copy
- `hmac.compare_digest` used (not `==`) to prevent timing attacks

## Acceptance

- `pytest tests/unit/workflows/ -q` green
- `mypy src/hestia` reports 0 new errors
- `ruff check src/ tests/` clean on changed files
- `.kimi-done` includes `LOOP=L148`
