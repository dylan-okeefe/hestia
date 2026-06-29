"""Context Lab API routes for prompt preview and budget tuning."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from hestia.commands.preview_prompt import _build_report
from hestia.web.context import WebContext, get_web_context

router = APIRouter()


@router.post("/context-lab/preview")
async def preview_prompt(
    request: Request,
    ctx: WebContext = Depends(get_web_context),  # noqa: B008
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Dry-run the prompt assembly and return layer breakdown + budget.

    Scopes memory epoch to the currently authenticated user.
    """
    payload = payload or {}

    platform = getattr(request.state, "platform", None)
    platform_user = getattr(request.state, "platform_user", None)

    # If auth is enabled but no session, still allow the call but memory
    # epoch will be unscoped (shows all memories). This is acceptable for
    # a diagnostic tool run by the operator.

    report = await _build_report(
        app=ctx.app,
        identity_tokens=payload.get("identity_tokens"),
        memory_tokens=payload.get("memory_tokens"),
        context_length=payload.get("context_length"),
        sample_history_turns=payload.get("history_turns", 10),
        platform=platform,
        platform_user=platform_user,
    )

    return {
        "context_length": report.ctx_len,
        "budget": report.budget,
        "empty_used": report.empty_used,
        "history_used": report.history_used,
        "history_kept": report.history_kept,
        "history_truncated": report.history_truncated,
        "layers": [
            {
                "name": layer.name,
                "tokens": layer.tokens,
                "truncated": layer.truncated,
                "text": layer.text,
            }
            for layer in report.layers
            if layer.text and layer.name not in ("assembled_system", "new_user_msg")
        ],
        "assembled_system": next(
            (layer.text for layer in report.layers if layer.name == "assembled_system"), ""
        ),
        "assembled_tokens": next(
            (layer.tokens for layer in report.layers if layer.name == "assembled_system"), 0
        ),
    }
