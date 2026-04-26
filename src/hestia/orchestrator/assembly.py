"""Turn assembly phase: prepares context, tools, slot, and history."""

import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import TYPE_CHECKING

from hestia.core.clock import utcnow
from hestia.orchestrator.types import Turn, TurnContext, TurnState
from hestia.style.context import format_style_prefix_from_data

if TYPE_CHECKING:
    from hestia.config import StyleConfig
    from hestia.context.builder import ContextBuilder
    from hestia.core.types import Session
    from hestia.inference.slot_manager import SlotManager
    from hestia.persistence.sessions import SessionStore
    from hestia.policy.engine import PolicyEngine
    from hestia.reflection.store import ProposalStore
    from hestia.skills.index import SkillIndexBuilder
    from hestia.style.store import StyleProfileStore
    from hestia.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

TransitionCallback = Callable[[Turn, TurnState, str], Awaitable[None]]


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
        proposal_store: "ProposalStore | None" = None,
        style_store: "StyleProfileStore | None" = None,
        style_config: "StyleConfig | None" = None,
        slot_manager: "SlotManager | None" = None,
        skill_index_builder: "SkillIndexBuilder | None" = None,
    ):
        self._builder = context_builder
        self._tools = tool_registry
        self._policy = policy
        self._store = session_store
        self._proposal_store = proposal_store
        self._style_store = style_store
        self._style_config = style_config
        self._slot_manager = slot_manager
        self._skill_index_builder = skill_index_builder

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
        history = await self._store.get_messages(session.id)
        await self._store.append_message(session.id, ctx.user_message)
        ctx.running_history = history + [ctx.user_message]

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

        ctx.tools = self._tools.meta_tool_schemas()
        self._builder.set_style_prefix(style_prefix)
        if self._skill_index_builder is not None:
            skill_index = await self._skill_index_builder.build_index()
            self._builder.set_skill_index_prefix(skill_index.text)
        ctx.build_result = await self._builder.build(
            session=session,
            history=history,
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
