"""Turn assembly phase: prepares context, tools, slot, and history."""

import logging
import re
from datetime import timedelta
from typing import TYPE_CHECKING

from hestia.core.clock import utcnow
from hestia.core.types import ToolSchema
from hestia.orchestrator.mappers import message_domain_to_dto, message_dto_to_domain
from hestia.orchestrator.types import TransitionCallback, TurnContext, TurnState
from hestia.persistence.message_store import MessageStore
from hestia.style.context import format_style_prefix_from_data

if TYPE_CHECKING:
    from hestia.config import StyleConfig
    from hestia.context.builder import ContextBuilder
    from hestia.core.types import Session
    from hestia.inference.slot_manager import SlotManager
    from hestia.persistence.message_store import MessageStore
    from hestia.persistence.session_store import SessionStore
    from hestia.policy.engine import PolicyEngine
    from hestia.reflection.store import ProposalStore
    from hestia.style.store import StyleProfileStore
    from hestia.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# Lightweight heuristic: first-turn greetings/small-talk should not trigger
# the meta-tool round-trip (list_tools / describe_tool / call_tool). This
# avoids the "Working: list_tools..." status and the extra latency on a
# simple "hey".
_GREETING_RE = re.compile(
    r"^\s*("
    r"hey|hi|hello|yo|hiya|howdy|"
    r"good\s+(morning|afternoon|evening)|"
    r"what'?s\s+up|sup|"
    r"how\s+(are|r)\s+(you|u|ya)|"
    r"how'?s\s+it\s+going|how\s+do\s+you\s+do"
    r")\s*[!?.]*\s*$",
    re.IGNORECASE,
)


def _is_greeting_or_smalltalk(text: str | None) -> bool:
    if not text:
        return False
    stripped = text.strip()
    return len(stripped) <= 60 and _GREETING_RE.match(stripped) is not None


class TurnAssembly:
    """Prepares a turn for execution by building context, injecting style and
    voice prompt prefixes, reading proposals, and acquiring slots."""

    def __init__(
        self,
        *,
        context_builder: "ContextBuilder",
        tool_registry: "ToolRegistry",
        policy: "PolicyEngine",
        session_store: "SessionStore",
        message_store: "MessageStore | None" = None,
        proposal_store: "ProposalStore | None" = None,
        style_store: "StyleProfileStore | None" = None,
        style_config: "StyleConfig | None" = None,
        slot_manager: "SlotManager | None" = None,
    ):
        self._builder = context_builder
        self._tools = tool_registry
        self._policy = policy
        self._store = session_store
        self._message_store = message_store or MessageStore(session_store._db)
        self._proposal_store = proposal_store
        self._style_store = style_store
        self._style_config = style_config
        self._slot_manager = slot_manager

    async def prepare(
        self,
        session: "Session",
        ctx: TurnContext,
        transition: TransitionCallback,
    ) -> None:
        """Prepare context, tools, slot, and history for the inference loop."""
        await transition(ctx.turn, TurnState.BUILDING_CONTEXT, "")
        all_tool_names = self._tools.list_names()
        ctx.allowed_tools = self._policy.filter_tools(
            session, all_tool_names, self._tools
        )
        history = await self._message_store.get_messages(session.id)
        history_domain = [message_dto_to_domain(dto) for dto in history]
        await self._message_store.append_message(
            session.id,
            message_domain_to_dto(ctx.user_message, session.id, idx=0),
        )
        ctx.running_history = history_domain + [ctx.user_message]

        effective_system_prompt = ctx.system_prompt
        if self._proposal_store is not None and not history:
            pending_count = await self._proposal_store.pending_count()
            if pending_count > 0:
                effective_system_prompt = (
                    f"You have {pending_count} pending reflection "
                    "proposal(s) from the last review. If the user "
                    "greets you or asks 'what's new', summarize the "
                    "top 3 and ask whether to accept/reject/defer. "
                    "Do not apply any proposal without an explicit "
                    f"accept.\n\n{ctx.system_prompt}"
                )

        style_prefix: str | None = None
        if (
            self._style_store is not None
            and self._style_config is not None
            and self._style_config.enabled
        ):
            since = utcnow() - timedelta(days=self._style_config.lookback_days)
            turn_count = await self._style_store.count_turns_in_window(
                session.platform, session.platform_user, since
            )
            if turn_count >= self._style_config.min_turns_to_activate:
                metrics = await self._style_store.get_profile_dict(
                    session.platform, session.platform_user
                )
                style_prefix = format_style_prefix_from_data(metrics)

        if ctx.voice_reply:
            effective_system_prompt = (
                "You are replying via voice message. Use plain, natural "
                "language. Avoid markdown, code blocks, bullet lists, tables, "
                "and emoji. Keep your response concise and easy to speak "
                "aloud.\n\n"
                + effective_system_prompt
            )

        if ctx.resolved_user is not None:
            user = ctx.resolved_user
            user_context = f"Current user: {user.display_name}"
            if user.role:
                user_context += f" ({user.role})"
            if user.notes:
                user_context += f"\nNotes: {user.notes}"
            effective_system_prompt = f"{user_context}\n\n{effective_system_prompt}"

        ctx.tools = self._tools.meta_tool_schemas()
        # save_memory is first-class (card #60): durable personal facts
        # surface inside casual conversation, where the system prompt forbids
        # the meta-tools (rules 3/4). Direct exposure makes rule 6
        # ("immediately use save_memory") actionable without describe_tool.
        save_schema = self._tools.direct_schema(
            "save_memory",
            description=(
                "Persist a durable fact the user shared: identity, family, "
                "living situation, personal preferences, corrections, or "
                "anything they will expect you to remember later. Call this "
                "proactively DURING casual conversation whenever such a fact "
                "appears, even when you otherwise reply directly without "
                "tools. scope: 'global' for identity/durable preferences "
                "(always loaded), 'topic' for conversation-scoped facts "
                "(default). tags: optional comma-separated categories."
            ),
        )
        if isinstance(save_schema, ToolSchema):
            ctx.tools = [*ctx.tools, save_schema]
        if not history and _is_greeting_or_smalltalk(ctx.user_message.content):
            logger.debug("First message looks like a greeting; removing tools for direct reply")
            ctx.tools = []

        self._builder.set_style_prefix(style_prefix)
        ctx.build_result = await self._builder.build(
            session=session,
            history=history_domain,
            system_prompt=effective_system_prompt,
            tools=ctx.tools,
            new_user_message=ctx.user_message,
        )
        ctx.style_prefix = style_prefix

        ctx.slot_id = session.slot_id
        if self._slot_manager is not None:
            assignment = await self._slot_manager.acquire(session)
            ctx.slot_id = assignment.slot_id
            refreshed = await self._store.get_session(session.id)
            if refreshed is not None:
                session = refreshed

        ctx.session = session
