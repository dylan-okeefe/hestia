"""Turn finalization phase: slot save, trace recording, failure bundles, handoff."""

import json
import logging
import uuid
from typing import TYPE_CHECKING, Any

from hestia.core.clock import utcnow
from hestia.core.types import Message, Session
from hestia.errors import ContextTooLargeError, HestiaError, PersistenceError, classify_error
from hestia.orchestrator.types import TransitionCallback, Turn, TurnContext, TurnState
from hestia.persistence.failure_store import FailureBundle

if TYPE_CHECKING:
    from hestia.inference.slot_manager import SlotManager
    from hestia.memory.handoff import SessionHandoffSummarizer
    from hestia.persistence.failure_store import FailureStore
    from hestia.persistence.sessions import SessionStore
    from hestia.persistence.trace_store import TraceStore
    from hestia.policy.engine import PolicyEngine

logger = logging.getLogger(__name__)

class TurnFinalization:
    """Handles turn finalization concerns: slot save, trace recording,
    failure bundle recording, handoff summarization, and error sanitization.
    """

    def __init__(
        self,
        *,
        slot_manager: "SlotManager | None" = None,
        failure_store: "FailureStore | None" = None,
        trace_store: "TraceStore | None" = None,
        handoff_summarizer: "SessionHandoffSummarizer | None" = None,
        policy: "PolicyEngine | None" = None,
        session_store: "SessionStore | None" = None,
    ):
        self._slot_manager = slot_manager
        self._failure_store = failure_store
        self._trace_store = trace_store
        self._handoff_summarizer = handoff_summarizer
        self._policy = policy
        self._store = session_store

    @staticmethod
    def sanitize_user_error(error: Exception) -> str:
        """Return a user-facing message for an unexpected error.

        HestiaError subclasses are intentionally raised with user-friendly
        messages, so they pass through. Everything else is sanitized to a
        generic message to avoid leaking internal details (SQL errors,
        file paths, stack traces) to end users.
        """
        from hestia.errors import (
            ContextTooLargeError,
            InferenceTimeoutError,
            MaxIterationsError,
            PolicyFailureError,
            ToolExecutionError,
        )

        if isinstance(error, InferenceTimeoutError):
            return "The AI is taking longer than expected. Try again in a moment."
        if isinstance(error, ContextTooLargeError):
            return (
                "Our conversation has grown very long. I'll summarize and continue "
                "— just ask your next question."
            )
        if isinstance(error, ToolExecutionError):
            return (
                f"I tried to use the {error.tool_name} tool but it failed. "
                f"You can retry or try a different approach."
            )
        if isinstance(error, MaxIterationsError):
            return "I'm having trouble responding right now. Please try again."
        if isinstance(error, PolicyFailureError):
            return "I'm having trouble responding right now. Please try again."
        if isinstance(error, HestiaError):
            return str(error)
        return "Something went wrong. The operator has been notified."

    async def finalize_turn(
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
        if self._store is not None:
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

    async def handle_context_too_large(
        self,
        ctx: TurnContext,
        exc: ContextTooLargeError,
        trace_record_id: str | None,
        transition: TransitionCallback,
    ) -> str | None:
        """Handle ContextTooLargeError: handoff, transition, warning, record failure."""
        session = ctx.session
        turn = ctx.turn
        await self.summarize_handoff(session)
        if turn.state not in (TurnState.DONE, TurnState.FAILED):
            await transition(turn, TurnState.FAILED, "")
            turn.error = str(exc)
            raw_budget = (
                self._policy.turn_token_budget(session)
                if self._policy is not None
                else None
            )
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
        return await self.record_failure_if_enabled(
            session,
            turn,
            exc,
            ctx.user_message,
            "context_too_large",
            ctx.allowed_tools,
            ctx.tool_chain,
            trace_record_id,
        )

    async def handle_unexpected_error(
        self,
        ctx: TurnContext,
        error: Exception,
        trace_record_id: str | None,
        transition: TransitionCallback,
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
            sanitized = self.sanitize_user_error(error)
            try:
                await ctx.respond_callback(f"Error delivering response: {sanitized}")
            except Exception as notify_err:
                logger.warning(
                    "Failed to send post-terminal error notification: %s",
                    notify_err,
                )
        else:
            await transition(turn, TurnState.FAILED, "")
            turn.error = str(error)
            sanitized = self.sanitize_user_error(error)
            await ctx.respond_callback(f"Error: {sanitized}")
        return await self.record_failure_if_enabled(
            session,
            turn,
            error,
            ctx.user_message,
            "exception",
            ctx.allowed_tools,
            ctx.tool_chain,
            trace_record_id,
        )

    async def record_failure_if_enabled(
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
            bundle = self.build_failure_bundle(
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

    def build_failure_bundle(
        self,
        *,
        session: Session,
        turn: Turn,
        error: Exception,
        user_input: str,
        failure_kind: str,
        allowed_tools: list[str] | None,
        tool_chain: list[str],
    ) -> FailureBundle:
        """Construct a FailureBundle from common turn state.

        Centralises slot snapshot, policy snapshot JSON, and input summary
        truncation; previously duplicated across two except blocks.
        """
        if failure_kind == "context_too_large":
            failure_class = "context_overflow"
            severity = "medium"
        else:
            failure_class, severity = classify_error(error)
            failure_class = failure_class.value

        raw_summary = user_input
        user_input_summary = raw_summary[:200] + "..." if len(raw_summary) > 200 else raw_summary

        reasoning_budget = turn.reasoning_budget
        if reasoning_budget is None and self._policy is not None:
            reasoning_budget = self._policy.reasoning_budget(session, turn.iterations)
        policy_snapshot = json.dumps(
            {
                "reasoning_budget": reasoning_budget,
                "turn_token_budget": (
                    self._policy.turn_token_budget(session) if self._policy is not None else None
                ),
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

    async def summarize_handoff(self, session: Session) -> None:
        """Generate and store a handoff summary for the session (best-effort).

        If a handoff summarizer is configured, fetches the session history
        and generates a summary before archiving.
        """
        if self._handoff_summarizer is None or self._store is None:
            return
        try:
            history = await self._store.get_messages(session.id)
            await self._handoff_summarizer.summarize_and_store(session, history)
        except Exception:  # noqa: BLE001
            logger.warning("Handoff summarizer failed for %s", session.id, exc_info=True)
