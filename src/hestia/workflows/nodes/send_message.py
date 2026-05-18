"""Send message node: delivers a message via platform adapter."""

from __future__ import annotations

import asyncio
from typing import Any

from hestia.app import AppContext
from hestia.platforms.notifier import PlatformNotifier
from hestia.workflows.interpolation import interpolate
from hestia.workflows.models import WorkflowNode
from hestia.workflows.response_store import DEFAULT_RESPONSE_STORE


class SendMessageNode:
    """Sends a message to a user via a platform notifier."""

    async def execute(
        self,
        app: AppContext,
        node: WorkflowNode,
        inputs: dict[str, Any],
    ) -> Any:
        """Send a message to the configured platform and user.

        Args:
            app: Application context.
            node: The workflow node.
            inputs: Resolved inputs for this node.

        Returns:
            Dict with send status and metadata. If ``requires_response`` is
            enabled, includes ``response`` and ``timed_out`` keys.

        Raises:
            ValueError: If ``platform``, ``target_user``/``user``,
            or ``message``/``text`` is missing.
        """
        platform = _resolve("platform", node, inputs)
        user = _resolve("target_user", node, inputs, fallback_key="user")
        text = _resolve("message", node, inputs, fallback_key="text")

        if text and isinstance(text, str):
            text = interpolate(text, inputs)

        if not platform:
            raise ValueError(
                "SendMessageNode requires 'platform' in config or inputs"
            )
        if not user:
            raise ValueError(
                "SendMessageNode requires 'target_user' (or 'user') in config or inputs"
            )
        if not text:
            raise ValueError(
                "SendMessageNode requires 'message' (or 'text') in config or inputs"
            )

        requires_response = node.config.get("requires_response", False)
        if not requires_response:
            notifier = PlatformNotifier(app.config)
            success = await notifier.send(platform, user, text)
            return {
                "sent": success,
                "platform": platform,
                "user": user,
                "text": text,
            }

        # Interactive mode: send message and wait for response
        timeout_seconds = node.config.get("timeout_seconds", 300)
        response_type = node.config.get("response_type", "buttons")
        buttons = node.config.get("buttons", ["Approve", "Deny"])

        if platform == "telegram":
            try:
                int(user)
            except ValueError:
                raise ValueError(f"Invalid Telegram chat ID: {user}")

        store = DEFAULT_RESPONSE_STORE
        request_id, future = store.create(platform, user)

        notifier = PlatformNotifier(app.config)
        if response_type == "buttons":
            success = await notifier.send_interactive(
                platform, user, text, buttons, request_id
            )
        else:
            success = await notifier.send(platform, user, text)

        if not success:
            store.cancel(request_id)
            return {
                "sent": False,
                "platform": platform,
                "user": user,
                "text": text,
                "response": None,
                "timed_out": False,
            }

        try:
            response = await asyncio.wait_for(future, timeout=timeout_seconds)
            return {
                "sent": True,
                "platform": platform,
                "user": user,
                "text": text,
                "response": response,
                "timed_out": False,
            }
        except TimeoutError:
            store.cancel(request_id)
            return {
                "sent": True,
                "platform": platform,
                "user": user,
                "text": text,
                "response": None,
                "timed_out": True,
            }


def _resolve(
    key: str, node: WorkflowNode, inputs: dict[str, Any], fallback_key: str | None = None
) -> Any:
    """Resolve a value from ``inputs`` or ``node.config``.

    If ``fallback_key`` is provided, it is tried after ``key``.
    """
    value = inputs.get(key)
    if value is not None:
        return value
    if fallback_key is not None:
        value = inputs.get(fallback_key)
        if value is not None:
            return value
    value = node.config.get(key)
    if value is not None:
        return value
    if fallback_key is not None:
        return node.config.get(fallback_key)
    return None
