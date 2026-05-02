"""Send message node: delivers a message via platform adapter."""

from __future__ import annotations

from typing import Any

from hestia.app import AppContext
from hestia.platforms.notifier import PlatformNotifier
from hestia.workflows.models import WorkflowNode


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
            Dict with send status and metadata.

        Raises:
            ValueError: If ``platform``, ``target_user``/``user``,
            or ``message``/``text`` is missing.
        """
        platform = _resolve("platform", node, inputs)
        user = _resolve("target_user", node, inputs, fallback_key="user")
        text = _resolve("message", node, inputs, fallback_key="text")

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

        notifier = PlatformNotifier(app.config)
        success = await notifier.send(platform, user, text)

        return {
            "sent": success,
            "platform": platform,
            "user": user,
            "text": text,
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
