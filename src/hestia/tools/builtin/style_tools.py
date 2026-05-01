"""Style profile tools — show, reset metric, reset profile."""

from collections.abc import Callable, Coroutine
from typing import Any

from hestia.runtime_context import current_platform, current_platform_user
from hestia.style.store import StyleProfileStore
from hestia.tools.capabilities import SELF_MANAGEMENT
from hestia.tools.metadata import tool


def make_show_style_profile_tool(
    style_store: StyleProfileStore,
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Create a show_style_profile tool bound to a StyleProfileStore instance."""

    @tool(
        name="show_style_profile",
        public_description="Show the current user's style profile.",
        tags=["style", "builtin"],
        capabilities=[SELF_MANAGEMENT],
    )
    async def show_style_profile() -> str:
        """Show the style profile for the current platform user.

        Uses runtime context set by the orchestrator during process_turn.

        Returns:
            Formatted style metrics or a message if no profile exists.
        """
        platform = current_platform.get()
        platform_user = current_platform_user.get()
        if not platform or not platform_user:
            return "No platform identity in current context."

        metrics = await style_store.list_metrics(platform, platform_user)
        if not metrics:
            return f"No style profile found for {platform}:{platform_user}."

        lines = [f"Style profile for {platform}:{platform_user}"]
        for m in metrics:
            updated = m.updated_at.strftime("%Y-%m-%d %H:%M")
            lines.append(f"  {m.metric}: {m.value_json} (updated {updated})")
        return "\n".join(lines)

    return show_style_profile


def make_reset_style_metric_tool(
    style_store: StyleProfileStore,
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Create a reset_style_metric tool bound to a StyleProfileStore instance."""

    @tool(
        name="reset_style_metric",
        public_description="Reset a single style metric. Params: metric (str).",
        tags=["style", "builtin"],
        capabilities=[SELF_MANAGEMENT],
        requires_confirmation=True,
    )
    async def reset_style_metric(metric: str) -> str:
        """Reset a single style metric for the current platform user.

        Args:
            metric: Metric name to reset (e.g., 'formality', 'preferred_length')

        Returns:
            Confirmation or error message.
        """
        platform = current_platform.get()
        platform_user = current_platform_user.get()
        if not platform or not platform_user:
            return "No platform identity in current context."

        deleted = await style_store.delete_metric(platform, platform_user, metric)
        if deleted:
            return f"Reset metric '{metric}' for {platform}:{platform_user}."
        return f"Metric '{metric}' not found for {platform}:{platform_user}."

    return reset_style_metric


def make_reset_style_profile_tool(
    style_store: StyleProfileStore,
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Create a reset_style_profile tool bound to a StyleProfileStore instance."""

    @tool(
        name="reset_style_profile",
        public_description="Reset the entire style profile for the current user.",
        tags=["style", "builtin"],
        capabilities=[SELF_MANAGEMENT],
        requires_confirmation=True,
    )
    async def reset_style_profile() -> str:
        """Reset the entire style profile for the current platform user.

        Returns:
            Confirmation or error message.
        """
        platform = current_platform.get()
        platform_user = current_platform_user.get()
        if not platform or not platform_user:
            return "No platform identity in current context."

        deleted = await style_store.delete_profile(platform, platform_user)
        return f"Reset style profile for {platform}:{platform_user} ({deleted} metrics removed)."

    return reset_style_profile
