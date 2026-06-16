"""Orchestrator engine for managing turn execution."""

import logging
import uuid
from pathlib import Path
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
from hestia.orchestrator.assembly import TurnAssembly
from hestia.orchestrator.execution import ConfirmCallback as ConfirmCallback
from hestia.orchestrator.execution import TurnExecution
from hestia.orchestrator.finalization import TurnFinalization
from hestia.orchestrator.handoff_service import HandoffService
from hestia.orchestrator.mappers import (
    message_domain_to_dto,
    turn_domain_to_dto,
    turn_transition_domain_to_dto,
)
from hestia.orchestrator.transitions import assert_transition
from hestia.orchestrator.types import (
    ResponseCallback,
    StreamCallback,
    Turn,
    TurnContext,
    TurnState,
    TurnTransition,
)
from hestia.persistence.message_store import MessageStore
from hestia.persistence.session_store import SessionStore
from hestia.persistence.turn_store import TurnStore
from hestia.persistence.users import User
from hestia.platforms.base import Platform
from hestia.policy.engine import PolicyEngine
from hestia.reflection.store import ProposalStore
from hestia.runtime_context import (
    current_platform,
    current_platform_user,
    current_session_id,
    current_trace_store,
    current_turn_id,
)
from hestia.security import InjectionScanner
from hestia.tools.checkpoint import CheckpointManager
from hestia.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from hestia.config import StyleConfig
    from hestia.events.bus import EventBus
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
        message_store: MessageStore | None = None,
        turn_store: TurnStore | None = None,
        handoff_service: HandoffService | None = None,
        confirm_callback: ConfirmCallback | None = None,
        max_iterations: int = 10,
        max_tool_calls_per_turn: int = 10,
        max_tokens: int = 1024,
        default_reasoning_budget: int = 2048,
        slot_manager: SlotManager | None = None,
        failure_store: "FailureStore | None" = None,
        trace_store: "TraceStore | None" = None,
        injection_scanner: InjectionScanner | None = None,
        proposal_store: ProposalStore | None = None,
        style_store: "StyleProfileStore | None" = None,
        style_config: "StyleConfig | None" = None,
        rate_limiter: SessionRateLimiter | None = None,
        stream: bool = False,
        event_bus: "EventBus | None" = None,
        checkpoint_manager: CheckpointManager | None = None,
        checkpoint_scope: list[str] | None = None,
        auto_rollback_on_failure: bool = False,
    ):
        """Initialize the orchestrator."""
        self._inference = inference
        self._store = session_store
        self._message_store = message_store or MessageStore(session_store._db)
        self._turn_store = turn_store or TurnStore(session_store._db)
        self._handoff_service = handoff_service or HandoffService(
            session_store, self._message_store, summarizer=None
        )
        message_store = self._message_store
        turn_store = self._turn_store
        handoff_service = self._handoff_service
        self._builder = context_builder
        self._tools = tool_registry
        self._policy = policy
        self._confirm_callback = confirm_callback
        self._max_iterations = max_iterations
        self._max_tool_calls_per_turn = max_tool_calls_per_turn
        self._max_tokens = max_tokens
        self._default_reasoning_budget = default_reasoning_budget
        self._slot_manager = slot_manager
        self._failure_store = failure_store
        self._trace_store = trace_store
        self._injection_scanner = injection_scanner
        self._proposal_store = proposal_store
        self._style_store = style_store
        self._style_config = style_config
        self._rate_limiter = rate_limiter
        self._stream = stream
        self._event_bus = event_bus
        self._checkpoint_manager = checkpoint_manager
        self._checkpoint_scope = checkpoint_scope
        self._auto_rollback_on_failure = auto_rollback_on_failure

        self._assembly = TurnAssembly(
            context_builder=context_builder,
            tool_registry=tool_registry,
            policy=policy,
            session_store=session_store,
            message_store=message_store,
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
            message_store=message_store,
            confirm_callback=confirm_callback,
            injection_scanner=injection_scanner,
            max_iterations=max_iterations,
            max_tool_calls_per_turn=max_tool_calls_per_turn,
            max_tokens=max_tokens,
            stream=stream,
            event_bus=event_bus,
        )

        self._finalization = TurnFinalization(
            slot_manager=slot_manager,
            failure_store=failure_store,
            trace_store=trace_store,
            handoff_service=handoff_service,
            policy=policy,
            session_store=session_store,
            turn_store=turn_store,
            checkpoint_manager=checkpoint_manager,
            auto_rollback_on_failure=auto_rollback_on_failure,
        )

    async def recover_stale_turns(self) -> int:
        """Mark any turns in non-terminal states as FAILED."""
        stale = await self._turn_store.list_stale_turns()
        count = 0
        for dto in stale:
            if dto.state not in (TurnState.DONE.value, TurnState.FAILED.value):
                await self._turn_store.fail_turn(
                    dto.id, error="Recovered after crash: turn was in non-terminal state"
                )
                count += 1
        return count

    async def close_session(self, session_id: str) -> None:
        """Close a session and generate a handoff summary."""
        session = await self._store.get_session(session_id)
        if session is None:
            logger.warning("close_session called for unknown session %s", session_id)
            return

        await self._handoff_service.generate_handoff_summary(session_id)

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
        stream_callback: StreamCallback | None = None,
        resolved_user: User | None = None,
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
        turn_token = current_turn_id.set("")

        try:
            turn = self._create_turn(session.id, user_message)
            await self._persist_turn(turn)
            current_turn_id.set(turn.id)

            if self._checkpoint_manager is not None:
                scope = self._checkpoint_scope or [str(Path.cwd())]
                self._checkpoint_manager.create(turn.id, scope)

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
                stream_callback=stream_callback,
                resolved_user=resolved_user,
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

            except IllegalTransitionError as exc:
                await self._set_typing(platform, platform_user, False)
                logger.error("Illegal transition: %s", exc)
                if turn.state not in (TurnState.DONE, TurnState.FAILED):
                    turn.state = TurnState.FAILED
                    turn.error = str(exc)
                    if self._turn_store is not None:
                        await self._turn_store.update_turn(turn_domain_to_dto(turn))
                try:
                    await ctx.respond_callback(
                        "An internal error occurred and the turn could not complete. "
                        "Please try again."
                    )
                except Exception as notify_err:  # noqa: BLE001
                    logger.warning(
                        "Failed to send illegal transition notification: %s",
                        notify_err,
                    )

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
            current_turn_id.reset(turn_token)

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
            reasoning_budget=self._default_reasoning_budget,
            transitions=[],
        )

    async def _persist_turn(self, turn: Turn) -> None:
        await self._turn_store.insert_turn(turn_domain_to_dto(turn))

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
        turn.last_transition_at = transition.at
        await self._turn_store.append_transition(
            turn_transition_domain_to_dto(turn.id, transition)
        )
        await self._turn_store.update_turn(turn_domain_to_dto(turn))

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
