"""Per-chat thinking/reasoning display gate (L250).

Decides whether the "💭 …" reasoning messages are shown for a given chat.
The gate is installed only by the Telegram runner wiring; other platforms
(CLI, Matrix) never install it and therefore keep the current always-show
behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hestia.orchestrator.types import ThinkingDisplayGate

if TYPE_CHECKING:
    from hestia.persistence.chat_settings import ChatSettingsStore

# Re-exported for callers that build gates (e.g. the Telegram runner wiring).
__all__ = [
    "ThinkingDisplayGate",
    "default_show_thinking",
    "make_thinking_display_gate",
    "resolve_show_thinking",
]


def default_show_thinking(platform_user: str, operator_user_id: str) -> bool:
    """Default thinking display for a chat with no explicit override.

    The operator's own chats default to showing reasoning; everyone else
    (other allowlisted users, group chats) defaults to hidden. An empty
    operator id means no operator is configured, so every chat defaults
    to hidden.
    """
    return bool(operator_user_id) and platform_user == operator_user_id


async def resolve_show_thinking(
    store: ChatSettingsStore,
    platform: str,
    platform_user: str,
    operator_user_id: str,
) -> bool:
    """Resolve the effective setting: stored override, else operator default."""
    stored = await store.get_show_thinking(platform, platform_user)
    if stored is not None:
        return stored
    return default_show_thinking(platform_user, operator_user_id)


def make_thinking_display_gate(
    store: ChatSettingsStore,
    operator_user_id: str,
) -> ThinkingDisplayGate:
    """Build a gate for TurnExecution backed by the per-chat settings store.

    Unknown platforms pass through as "show" — the gate only scopes Telegram
    chats, since the operator id is a Telegram user/chat id.
    """

    async def gate(platform: str, platform_user: str) -> bool:
        if platform != "telegram":
            return True
        return await resolve_show_thinking(store, platform, platform_user, operator_user_id)

    return gate
