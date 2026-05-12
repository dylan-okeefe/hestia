# L168 — Variable Interpolation & Webhook Route Extraction

**Status:** Spec only  
**Branch:** `feature/l168-variable-interpolation-and-webhook-extraction` (from `feature/workflow-builder-runtime`)  
**Depends on:** L154 (backend hardening)

## Intent

Two medium-priority items from the copilot review:

1. **COP-3:** The UI shows `{{node_id.field}}` template syntax in LLMDecisionNode and SendMessageNode, but the backend performs no interpolation. Users see placeholder syntax that does nothing.

2. **Architecture strain:** The `workflows.py` route file handles CRUD, versions, webhooks, test-runs, and dashboard queries. Webhook routes should be extracted into their own file.

## Review carry-forward

- *(none)*

## Scope

### §1 — Implement `{{variable}}` interpolation engine

Create `src/hestia/workflows/interpolation.py`:

```python
import re
from typing import Any

VAR_RE = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")

def interpolate(template: str, context: dict[str, Any]) -> str:
    """Replace {{key}} or {{node_id.field}} placeholders with values from context."""
    def _replacer(match: re.Match) -> str:
        key = match.group(1)
        parts = key.split(".")
        value = context
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part, "")
            else:
                value = ""
        return str(value) if value is not None else ""
    return VAR_RE.sub(_replacer, template)
```

Integrate into the workflow executor:
- Before sending a message via SendMessageNode, interpolate the message body.
- Before evaluating LLMDecisionNode prompt, interpolate variables.
- Context includes: node outputs, trigger payload, execution metadata.

**Commit:** `feat(workflows): add {{variable}} interpolation engine`

### §2 — Update UI to show live interpolation preview

In `web-ui/src/components/workflow-nodes/SendMessageNode.tsx` (and LLMDecisionNode):
- Add a "Preview" button or live preview area.
- When the user types `{{trigger.message}}`, show the interpolated result using mock data.
- If interpolation is disabled (no context available), show a helpful tooltip.

**Commit:** `feat(web-ui): add live interpolation preview to message nodes`

### §3 — Extract webhook routes from workflows.py

Create `src/hestia/web/routes/webhooks.py`:

Move all webhook-related endpoints from `workflows.py`:
- `POST /api/workflows/{id}/webhook` (register webhook)
- `POST /api/webhooks/{workflow_id}` (incoming webhook trigger)
- `GET /api/workflows/{id}/webhook/secret` (get/regenerate secret)

Update `src/hestia/web/api.py` to register the new router.

**Commit:** `refactor(api): extract webhook routes into dedicated webhooks.py`

### §4 — Add `is_rate_limited()` public method to auth manager (COP-7)

In `src/hestia/web/auth.py`, add:

```python
def is_rate_limited(self, user: str) -> bool:
    """Check if the user is currently rate-limited."""
    return self._is_rate_limited(user)
```

Update web routes to use the public method instead of accessing private attributes.

**Commit:** `refactor(auth): add public is_rate_limited() method to AuthManager`

### §5 — Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Acceptance

- `{{node_id.field}}` syntax is interpolated in SendMessageNode and LLMDecisionNode
- UI shows a live preview of interpolated values
- Webhook routes live in `webhooks.py`, not `workflows.py`
- `AuthManager.is_rate_limited()` is public and used by routes
- All quality gates pass

## Handoff

- Write `docs/handoffs/L168-variable-interpolation-and-webhook-extraction-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
