"""Orchestrator engine for managing turn execution."""

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from hestia.context.builder import ContextBuilder
from hestia.core.clock import utcnow
from hestia.core.inference import InferenceClient
from hestia.core.types import Message, Session, ToolCall
from hestia.errors import (
    ContextTooLargeError,
    HestiaError,
    IllegalTransitionError,
    PersistenceError,
    PlatformError,
    classify_error,
)
from hestia.inference.slot_manager import SlotManager
from hestia.memory.handoff import SessionHandoffSummarizer
from hestia.orchestrator.assembly import TurnAssembly
from hestia.orchestrator.execution import TurnExecution
from hestia.orchestrator.transitions import assert_transition
from hestia.orchestrator.types import ResponseCallback, Turn, TurnContext, TurnState, TurnTransition
from hestia.persistence.failure_store import FailureBundle
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
    from hestia.tools.metadata import ToolMetadata
    from hestia.tools.types import ToolCallResult

logger = logging.getLogger(__name__)


def _sanitize_user_error(error: Exception) -> str:
    """Return a user-facing message for an unexpected error.

    HestiaError subclasses are intentionally raised with user-friendly
    messages, so they pass through. Everything else is sanitized to a
    generic message to avoid leaking internal details (SQL errors,
    file paths, stack traces) to end users.
    """
    if isinstance(error, HestiaError):
        return str(error)
    return "Something went wrong. The operator has been notified."


# Callback types
ConfirmCallback = Callable[[str, dict[str, Any]], Awaitable[bool]]


class Orchestrator:
    """Manages turn execution through the state machine.

    The orchestrator is platform-agnostic. Platform adapters (CLI, Matrix,
    Telegram) provide callbacks for user confirmation and response delivery.
    """

    def __init__(
        self,
        inference: InferenceClient,
        session_store: SessionStore,
        context_builder: ContextBuilder,
        tool_registry: ToolRegistry,
        policy: PolicyEngine,
        confirm_callback: ConfirmCallback | None = None,
        max_iterations: int = 10,
        slot_manager: SlotManager | None = None,
        failure_store: "FailureStore | None" = None,
        trace_store: "TraceStore | None" = None,
        handoff_summarizer: SessionHandoffSummarizer | None = None,
        injection_scanner: InjectionScanner | None = None,
        proposal_store: ProposalStore | None = None,
        style_store: "StyleProfileStore | None" = None,
        style_config: "StyleConfig | None" = None,
    ):
        """Initialize the orchestrator.

        Args:
            inference: Client for LLM inference
            session_store: Persistence layer for sessions and turns
            context_builder: Builds message lists within token budget
            tool_registry: Registry for tool dispatch
            policy: Policy engine for decisions
            confirm_callback: Optional callback for tool confirmation
            max_iterations: Hard limit to prevent infinite tool loops
            slot_manager: Optional SlotManager for KV-cache slot management.
                When None, falls back to session.slot_id (legacy behavior).
            failure_store: Optional store for recording failure bundles.
            trace_store: Optional store for recording execution traces.
            handoff_summarizer: Optional summarizer for session-close summaries.
        """
        self._inference = inference
        self._store = session_store
        self._builder = context_builder
        self._tools = tool_registry
        self._policy = policy
        self._confirm_callback = confirm_callback
        self._max_iterations = max_iterations
        self._slot_manager = slot_manager
        self._failure_store = failure_store
        self._trace_store = trace_store
        self._handoff_summarizer = handoff_summarizer
        self._injection_scanner = injection_scanner
        self._proposal_store = proposal_store
        self._style_store = style_store
        self._style_config = style_config
        self._turn_assembly = TurnAssembly(
            context_builder=context_builder,
            tool_registry=tool_registry,
            policy=policy,
            session_store=session_store,
            proposal_store=proposal_store,
            style_store=style_store,
            style_config=style_config,
            slot_manager=slot_manager,
        )
        self._turn_execution = TurnExecution(
            tool_registry=tool_registry,
            inference_client=inference,
            policy=policy,
            context_builder=context_builder,
            session_store=session_store,
            confirm_callback=confirm_callback,
            injection_scanner=injection_scanner,
            max_iterations=max_iterations,
        )

    async def recover_stale_turns(self) -> int:
        """Mark any turns in non-terminal states as FAILED.

        Called on startup after a crash. Returns the number of turns recovered.

        Non-terminal states: RECEIVED, BUILDING_CONTEXT, AWAITING_MODEL,
        EXECUTING_TOOLS, AWAITING_USER, AWAITING_SUBAGENT, RETRYING.

        Terminal states: DONE, FAILED.
        """
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
        """Close a session, optionally generating a handoff summary.

        Archives the session and, if a handoff summarizer is configured,
        generates a summary of the conversation before archiving.
        """
        session = await self._store.get_session(session_id)
        if session is None:
            logger.warning("close_session called for unknown session %s", session_id)
            return

        if self._handoff_summarizer is not None:
            try:
                history = await self._store.get_messages(session_id)
                await self._handoff_summarizer.summarize_and_store(session, history)
            except Exception:  # noqa: BLE001 — handoff is best-effort
                logger.warning("Handoff summarizer failed for %s", session_id, exc_info=True)

        await self._store.archive_session(session_id)

    async def _set_typing(
        self, platform: Platform | None, platform_user: str | None, typing: bool
    ) -> None:
        """Set typing indicator on the platform (best-effort)."""
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

            async def _set_typing_bound(typing: bool) -> None:
                await self._set_typing(ctx.platform, ctx.platform_user, typing)

            try:
                await self._prepare_turn_context(session, ctx)
                await self._turn_execution.run(
                    ctx,
                    transition=self._safe_transition,
                    set_typing=_set_typing_bound,
                )

            except ContextTooLargeError as exc:
                await self._set_typing(platform, platform_user, False)
                trace_record_id = await self._handle_context_too_large(
                    ctx, exc, trace_record_id
                )

            except IllegalTransitionError:
                raise

            except Exception as e:
                await self._set_typing(platform, platform_user, False)
                trace_record_id = await self._handle_unexpected_error(
                    ctx, e, trace_record_id
                )

            finally:
                await self._finalize_turn(
                    ctx, turn_start_time, trace_record_id
                )

            return turn

        finally:
            current_session_id.reset(session_token)
            current_platform.reset(platform_token)
            current_platform_user.reset(platform_user_token)
            if trace_token is not None:
                current_trace_store.reset(trace_token)

    async def _prepare_turn_context(
        self,
        session: Session,
        ctx: TurnContext,
    ) -> None:
        """Prepare context, tools, slot, and history for the inference loop."""
        await self._turn_assembly.prepare(
            session=session,
            ctx=ctx,
            transition=self._safe_transition,
        )

    async def _execute_tool_calls(
        self, session: Session, tool_calls: list[ToolCall], allowed_tools: list[str] | None = None
    ) -> tuple[list[Message], list[str]]:
        """Delegate to TurnExecution (proxy for backward compatibility)."""
        return await self._turn_execution._execute_tool_calls(session, tool_calls, allowed_tools)

    async def _check_confirmation(
        self,
        *,
        tool: "ToolMetadata",
        tool_name: str,
        arguments: dict[str, Any],
        session: Session,
    ) -> "ToolCallResult | None":
        """Delegate to TurnExecution (proxy for backward compatibility)."""
        return await self._turn_execution._check_confirmation(
            tool=tool, tool_name=tool_name, arguments=arguments, session=session
        )

    async def _handle_context_too_large(
        self,
        ctx: TurnContext,
        exc: ContextTooLargeError,
        trace_record_id: str | None,
    ) -> str | None:
        """Handle ContextTooLargeError: handoff, transition, warning, record failure."""
        session = ctx.session
        turn = ctx.turn
        if self._handoff_summarizer is not None:
            try:
                history = await self._store.get_messages(session.id)
                await self._handoff_summarizer.summarize_and_store(session, history)
            except Exception:
                logger.warning(
                    "Handoff summarizer failed during overflow handling for %s",
                    session.id,
                    exc_info=True,
                )
        if turn.state not in (TurnState.DONE, TurnState.FAILED):
            await self._safe_transition(turn, TurnState.FAILED)
            turn.error = str(exc)
            raw_budget = self._policy.turn_token_budget(session)
            warning_text = (
                f"This session has grown past my context budget "
                f"({raw_budget:,} tokens per slot). I've saved a summary "
                "of our conversation. Type /reset to start fresh, and "
                "I'll keep the summary for reference."
            )
            if ctx.platform is not None:
                await ctx.platform.send_system_warning(ctx.platform_user or "", warning_text)
            else:
                await ctx.respond_callback(f"⚠️ {warning_text}")
        return await self._record_failure_if_enabled(
            session, turn, exc, ctx.user_message, "context_too_large",
            ctx.allowed_tools, ctx.tool_chain, trace_record_id,
        )

    async def _handle_unexpected_error(
        self,
        ctx: TurnContext,
        error: Exception,
        trace_record_id: str | None,
    ) -> str | None:
        """Handle unexpected errors: notify user, transition to FAILED, record failure."""
        turn = ctx.turn
        session = ctx.session
        if turn.state in (TurnState.DONE, TurnState.FAILED):
            logger.error(
                "Error after turn reached terminal state %s: %s",
                turn.state.value,
                error,
            )
            sanitized = _sanitize_user_error(error)
            try:
                await ctx.respond_callback(f"Error delivering response: {sanitized}")
            except Exception as notify_err:
                logger.warning(
                    "Failed to send post-terminal error notification: %s",
                    notify_err,
                )
        else:
            await self._safe_transition(turn, TurnState.FAILED)
            turn.error = str(error)
            sanitized = _sanitize_user_error(error)
            await ctx.respond_callback(f"Error: {sanitized}")
        return await self._record_failure_if_enabled(
            session, turn, error, ctx.user_message, "exception",
            ctx.allowed_tools, ctx.tool_chain, trace_record_id,
        )

    async def _record_failure_if_enabled(
        self,
        session: Session,
        turn: Turn,
        error: Exception,
        user_message: Message,
        failure_kind: str,
        allowed_tools: list[str] | None,
        tool_chain: list[str],
        trace_record_id: str | None,
    ) -> str | None:
        """Record a failure bundle if failure_store is configured."""
        if self._failure_store is None:
            return trace_record_id

        try:
            bundle = self._build_failure_bundle(
                session=session,
                turn=turn,
                error=error,
                user_input=user_message.content or "",
                failure_kind=failure_kind,
                allowed_tools=allowed_tools,
                tool_chain=tool_chain,
            )
            if bundle.trace_id is not None:
                trace_record_id = bundle.trace_id
            await self._failure_store.record(bundle)
        except Exception as record_err:  # noqa: BLE001
            logger.error("Failed to record failure bundle: %s", record_err)

        return trace_record_id

    async def _finalize_turn(
        self,
        ctx: TurnContext,
        turn_start_time: Any,
        trace_record_id: str | None,
    ) -> None:
        """Finalize turn: save slot, update turn, record trace, set artifact handles."""
        session = ctx.session
        turn = ctx.turn
        if turn.state == TurnState.DONE and self._slot_manager is not None:
            try:
                await self._slot_manager.save(session)
            except (OSError, PersistenceError) as e:
                logger.warning("Failed to save slot for session %s: %s", session.id, e)

        turn_end_time = utcnow()
        total_duration_ms = int((turn_end_time - turn_start_time).total_seconds() * 1000)

        turn.completed_at = turn_end_time
        await self._store.update_turn(turn)

        if self._trace_store is not None:
            try:
                from hestia.persistence.trace_store import TraceRecord

                raw_summary = ctx.user_message.content or ""
                if len(raw_summary) > 200:
                    user_input_summary = raw_summary[:200] + "..."
                else:
                    user_input_summary = raw_summary

                outcome = "success" if turn.state == TurnState.DONE else "failed"
                if turn.state not in (TurnState.DONE, TurnState.FAILED):
                    outcome = "partial"

                if trace_record_id is None:
                    trace_record_id = str(uuid.uuid4())

                trace = TraceRecord(
                    id=trace_record_id,
                    session_id=session.id,
                    turn_id=turn.id,
                    started_at=turn_start_time,
                    ended_at=turn_end_time,
                    user_input_summary=user_input_summary,
                    tools_called=ctx.tool_chain,
                    tool_call_count=len(ctx.tool_chain),
                    delegated=ctx.delegated,
                    outcome=outcome,
                    artifact_handles=ctx.artifact_handles,
                    prompt_tokens=ctx.total_prompt_tokens if ctx.total_prompt_tokens > 0 else None,
                    completion_tokens=(
                        ctx.total_completion_tokens if ctx.total_completion_tokens > 0 else None
                    ),
                    reasoning_tokens=(
                        ctx.total_reasoning_tokens if ctx.total_reasoning_tokens > 0 else None
                    ),
                    total_duration_ms=total_duration_ms,
                )
                await self._trace_store.record(trace)
            except Exception as trace_err:  # noqa: BLE001
                logger.error("Failed to record trace: %s", trace_err)

        turn.artifact_handles = list(ctx.artifact_handles)

    def _build_failure_bundle(
        self,
        *,
        session: Session,
        turn: Turn,
        error: Exception,
        user_input: str,
        failure_kind: str,
        allowed_tools: list[str] | None,
        tool_chain: list[str],
    ) -> "FailureBundle":
        """Construct a FailureBundle from common turn state.

        Centralises slot snapshot, policy snapshot JSON, and input summary
        truncation; previously duplicated across two except blocks."""
        if failure_kind == "context_too_large":
            failure_class = "context_overflow"
            severity = "medium"
        else:
            failure_class, severity = classify_error(error)
            failure_class = failure_class.value

        raw_summary = user_input
        user_input_summary = raw_summary[:200] + "..." if len(raw_summary) > 200 else raw_summary

        reasoning_budget = turn.reasoning_budget
        if reasoning_budget is None:
            reasoning_budget = self._policy.reasoning_budget(session, turn.iterations)
        policy_snapshot = json.dumps(
            {
                "reasoning_budget": reasoning_budget,
                "turn_token_budget": self._policy.turn_token_budget(session),
                "tool_filter_active": allowed_tools is not None,
            },
            default=str,
        )

        try:
            temp_value = None
            if session.temperature is not None:
                temp_value = session.temperature.value
            slot_snapshot = json.dumps(
                {
                    "slot_id": session.slot_id,
                    "temperature": temp_value,
                    "slot_saved_path": session.slot_saved_path,
                },
                default=str,
            )
        except (TypeError, AttributeError):
            slot_snapshot = json.dumps({"error": "slot snapshot serialization failed"})

        trace_id = None
        if self._trace_store is not None:
            trace_id = str(uuid.uuid4())

        return FailureBundle(
            id=str(uuid.uuid4()),
            session_id=session.id,
            turn_id=turn.id,
            failure_class=failure_class,
            severity=severity,
            error_message=str(error),
            tool_chain=json.dumps(tool_chain),
            created_at=utcnow(),
            request_summary=user_input_summary,
            policy_snapshot=policy_snapshot,
            slot_snapshot=slot_snapshot,
            trace_id=trace_id,
        )

    def _create_turn(self, session_id: str, user_message: Message) -> Turn:
        """Create a new Turn instance."""
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
        """Persist turn to database."""
        await self._store.insert_turn(turn)

    async def _transition(self, turn: Turn, to_state: TurnState, note: str = "") -> None:
        """Validate and execute a state transition."""
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
        """Validate and execute a state transition with IllegalTransitionError guard."""
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

