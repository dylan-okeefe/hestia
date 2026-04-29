"""Orchestrator engine for managing turn execution."""

import logging
import uuid
from typing import TYPE_CHECKING, Any

from hestia.context.builder import ContextBuilder
from hestia.core.clock import utcnow
from hestia.core.inference import InferenceClient
from hestia.core.rate_limiter import SessionRateLimiter
from hestia.core.types import Message, Session
from hestia.errors import (
    ContextTooLargeError,
    IllegalTransitionError,
    PlatformError,
)
from hestia.inference.slot_manager import SlotManager
from hestia.memory.handoff import SessionHandoffSummarizer
from hestia.orchestrator.assembly import TurnAssembly
from hestia.orchestrator.execution import ConfirmCallback as ConfirmCallback
from hestia.orchestrator.execution import TurnExecution
from hestia.orchestrator.finalization import TurnFinalization
from hestia.orchestrator.transitions import assert_transition
from hestia.orchestrator.types import ResponseCallback, Turn, TurnContext, TurnState, TurnTransition
from hestia.persistence.sessions import SessionStore
from hestia.platforms.base import Platform
from hestia.policy.engine import PolicyEngine
from hestia.reflection.store import ProposalStore
from hestia.runtime_context import (
    current_platform,
    current_platform_user,
    current_session_id,
    current_trace_store,
)
from hestia.security import InjectionScanner
from hestia.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from hestia.config import StyleConfig
    from hestia.persistence.failure_store import FailureStore
    from hestia.persistence.trace_store import TraceStore
    from hestia.style.store import StyleProfileStore

logger = logging.getLogger(__name__)


class Orchestrator:
    """Manages turn execution through the state machine."""

    def __init__(
        self,
        inference: InferenceClient,
        session_store: SessionStore,
        context_builder: ContextBuilder,
        tool_registry: ToolRegistry,
        policy: PolicyEngine,
        confirm_callback: ConfirmCallback | None = None,
        max_iterations: int = 10,
        max_tool_calls_per_turn: int = 10,
        slot_manager: SlotManager | None = None,
        failure_store: "FailureStore | None" = None,
        trace_store: "TraceStore | None" = None,
        handoff_summarizer: SessionHandoffSummarizer | None = None,
        injection_scanner: InjectionScanner | None = None,
        proposal_store: ProposalStore | None = None,
        style_store: "StyleProfileStore | None" = None,
        style_config: "StyleConfig | None" = None,
        rate_limiter: SessionRateLimiter | None = None,
    ):
        """Initialize the orchestrator."""
        self._inference = inference
        self._store = session_store
        self._builder = context_builder
        self._tools = tool_registry
        self._policy = policy
        self._confirm_callback = confirm_callback
        self._max_iterations = max_iterations
        self._max_tool_calls_per_turn = max_tool_calls_per_turn
        self._slot_manager = slot_manager
        self._failure_store = failure_store
        self._trace_store = trace_store
        self._handoff_summarizer = handoff_summarizer
        self._injection_scanner = injection_scanner
        self._proposal_store = proposal_store
        self._style_store = style_store
        self._style_config = style_config
        self._rate_limiter = rate_limiter

        self._assembly = TurnAssembly(
            context_builder=context_builder,
            tool_registry=tool_registry,
            policy=policy,
            session_store=session_store,
            proposal_store=proposal_store,
            style_store=style_store,
            style_config=style_config,
            slot_manager=slot_manager,
        )

        self._execution = TurnExecution(
            tool_registry=tool_registry,
            inference_client=inference,
            policy=policy,
            context_builder=context_builder,
            session_store=session_store,
            confirm_callback=confirm_callback,
            injection_scanner=injection_scanner,
            max_iterations=max_iterations,
            max_tool_calls_per_turn=max_tool_calls_per_turn,
        )

        self._finalization = TurnFinalization(
            slot_manager=slot_manager,
            failure_store=failure_store,
            trace_store=trace_store,
            handoff_summarizer=handoff_summarizer,
            policy=policy,
            session_store=session_store,
        )

    async def recover_stale_turns(self) -> int:
        """Mark any turns in non-terminal states as FAILED."""
        stale = await self._store.list_stale_turns()
        count = 0
        for turn in stale:
            if turn.state not in (TurnState.DONE, TurnState.FAILED):
                await self._store.fail_turn(
                    turn.id, error="Recovered after crash: turn was in non-terminal state"
                )
                count += 1
        return count

    async def close_session(self, session_id: str) -> None:
        """Close a session, optionally generating a handoff summary."""
        session = await self._store.get_session(session_id)
        if session is None:
            logger.warning("close_session called for unknown session %s", session_id)
            return

        if self._handoff_summarizer is not None:
            try:
                history = await self._store.get_messages(session_id)
                await self._handoff_summarizer.summarize_and_store(session, history)
            except Exception:  # noqa: BLE001
                logger.warning("Handoff summarizer failed for %s", session_id, exc_info=True)

        await self._store.archive_session(session_id)

    async def _set_typing(
        self, platform: Platform | None, platform_user: str | None, typing: bool
    ) -> None:
        if platform is not None and platform_user is not None:
            try:
                await platform.set_typing(platform_user, typing)
            except (PlatformError, OSError) as e:
                logger.debug("Failed to set typing: %s", e)

    async def process_turn(
        self,
        session: Session,
        user_message: Message,
        respond_callback: ResponseCallback,
        system_prompt: str = "You are a helpful assistant.",
        platform: Platform | None = None,
        platform_user: str | None = None,
        voice_reply: bool = False,
    ) -> Turn:
        """Process a single user turn through the state machine."""
        if self._rate_limiter is not None and not self._rate_limiter.allow(session.id):
            await respond_callback(
                "Rate limit exceeded. Please wait a moment before sending another message."
            )
            raise PlatformError("Rate limit exceeded for session")  # noqa: TRY003
        session_token = current_session_id.set(session.id)
        platform_token = current_platform.set(session.platform)
        platform_user_token = current_platform_user.set(session.platform_user)
        trace_token: Any = None
        if self._trace_store is not None:
            trace_token = current_trace_store.set(self._trace_store)

        try:
            turn = self._create_turn(session.id, user_message)
            await self._persist_turn(turn)
            await self._set_typing(platform, platform_user, True)

            turn_start_time = utcnow()
            trace_record_id: str | None = None

            ctx = TurnContext(
                turn=turn,
                user_message=user_message,
                system_prompt=system_prompt,
                respond_callback=respond_callback,
                platform=platform,
                platform_user=platform_user,
                session=session,
                voice_reply=voice_reply,
            )

            try:
                await self._assembly.prepare(session, ctx, self._safe_transition)
                await self._execution.run(
                    ctx, self._safe_transition,
                    lambda typing: self._set_typing(ctx.platform, ctx.platform_user, typing),
                )

            except ContextTooLargeError as exc:
                await self._set_typing(platform, platform_user, False)
                trace_record_id = await self._finalization.handle_context_too_large(
                    ctx, exc, trace_record_id, self._safe_transition
                )

            except IllegalTransitionError:
                raise

            except Exception as e:  # noqa: BLE001 — turn boundary safety net
                await self._set_typing(platform, platform_user, False)
                trace_record_id = await self._finalization.handle_unexpected_error(
                    ctx, e, trace_record_id, self._safe_transition
                )

            finally:
                await self._finalization.finalize_turn(ctx, turn_start_time, trace_record_id)

            return turn

        finally:
            current_session_id.reset(session_token)
            current_platform.reset(platform_token)
            current_platform_user.reset(platform_user_token)
            if trace_token is not None:
                current_trace_store.reset(trace_token)

    def _create_turn(self, session_id: str, user_message: Message) -> Turn:
        return Turn(
            id=str(uuid.uuid4()),
            session_id=session_id,
            state=TurnState.RECEIVED,
            user_message=user_message,
            started_at=utcnow(),
            completed_at=None,
            iterations=0,
            tool_calls_made=0,
            final_response=None,
            error=None,
            transitions=[],
        )

    async def _persist_turn(self, turn: Turn) -> None:
        await self._store.insert_turn(turn)

    async def _transition(self, turn: Turn, to_state: TurnState, note: str = "") -> None:
        assert_transition(turn.state, to_state)
        transition = TurnTransition(
            from_state=turn.state,
            to_state=to_state,
            at=utcnow(),
            note=note,
        )
        turn.transitions.append(transition)
        turn.state = to_state
        await self._store.append_transition(turn.id, transition)
        await self._store.update_turn(turn)

    async def _safe_transition(self, turn: Turn, to_state: TurnState, note: str = "") -> None:
        try:
            await self._transition(turn, to_state, note)
        except IllegalTransitionError:
            logger.error(
                "Illegal transition from %s to %s for turn %s",
                turn.state.value,
                to_state.value,
                turn.id,
            )
            raise
