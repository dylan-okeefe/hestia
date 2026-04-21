"""Orchestrator engine for managing turn execution."""

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from hestia.context.builder import BuildResult, ContextBuilder
from hestia.core.clock import utcnow
from hestia.core.inference import InferenceClient
from hestia.core.types import Message, Session, ToolCall, ToolSchema
from hestia.errors import (
    ContextTooLargeError,
    EmptyResponseError,
    IllegalTransitionError,
    MaxIterationsError,
    PersistenceError,
    PlatformError,
    PolicyFailureError,
    classify_error,
)
from hestia.inference.slot_manager import SlotManager
from hestia.memory.handoff import SessionHandoffSummarizer
from hestia.orchestrator.transitions import assert_transition
from hestia.orchestrator.types import Turn, TurnState, TurnTransition
from hestia.persistence.failure_store import FailureBundle
from hestia.persistence.sessions import SessionStore
from hestia.platforms.base import Platform
from hestia.policy.engine import PolicyEngine, RetryAction
from hestia.reflection.store import ProposalStore
from hestia.runtime_context import current_platform, current_platform_user
from hestia.security import InjectionScanner
from hestia.style.context import format_style_prefix_from_data
from hestia.tools.builtin import current_session_id, current_trace_store
from hestia.tools.metadata import ToolMetadata
from hestia.tools.registry import ToolNotFoundError, ToolRegistry
from hestia.tools.types import ToolCallResult

if TYPE_CHECKING:
    from hestia.config import StyleConfig
    from hestia.persistence.failure_store import FailureStore
    from hestia.persistence.trace_store import TraceStore
    from hestia.style.store import StyleProfileStore

logger = logging.getLogger(__name__)


# Callback types
ConfirmCallback = Callable[[str, dict[str, Any]], Awaitable[bool]]
ResponseCallback = Callable[[str], Awaitable[None]]


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
            tool_chain: list[str] = []
            delegated: bool = False
            await self._set_typing(platform, platform_user, True)

            turn_start_time = utcnow()
            total_prompt_tokens = 0
            total_completion_tokens = 0
            total_reasoning_tokens = 0
            artifact_handles: list[str] = []
            trace_record_id: str | None = None
            allowed_tools: list[str] | None = None

            try:
                (
                    session, build_result, tools, slot_id_to_use,
                    running_history, style_prefix, allowed_tools,
                ) = await self._prepare_turn_context(
                    session, turn, user_message, system_prompt
                )
                (
                    content, tool_chain, artifact_handles,
                    total_prompt_tokens, total_completion_tokens,
                    total_reasoning_tokens, delegated,
                ) = await self._run_inference_loop(
                    session=session,
                    turn=turn,
                    build_result=build_result,
                    tools=tools,
                    slot_id_to_use=slot_id_to_use,
                    respond_callback=respond_callback,
                    platform=platform,
                    platform_user=platform_user,
                    user_message=user_message,
                    allowed_tools=allowed_tools,
                    style_prefix=style_prefix,
                    system_prompt=system_prompt,
                    running_history=running_history,
                    tool_chain=tool_chain,
                    artifact_handles=artifact_handles,
                    total_prompt_tokens=total_prompt_tokens,
                    total_completion_tokens=total_completion_tokens,
                    total_reasoning_tokens=total_reasoning_tokens,
                    delegated=delegated,
                )

            except ContextTooLargeError as exc:
                await self._set_typing(platform, platform_user, False)
                trace_record_id = await self._handle_context_too_large(
                    session, turn, exc, user_message, platform, platform_user,
                    respond_callback, allowed_tools, tool_chain, trace_record_id,
                )

            except IllegalTransitionError:
                raise

            except Exception as e:
                await self._set_typing(platform, platform_user, False)
                trace_record_id = await self._handle_unexpected_error(
                    session, turn, e, user_message, platform, platform_user,
                    respond_callback, allowed_tools, tool_chain, trace_record_id,
                )

            finally:
                await self._finalize_turn(
                    session, turn, user_message, turn_start_time, tool_chain, delegated,
                    artifact_handles, trace_record_id,
                    total_prompt_tokens, total_completion_tokens, total_reasoning_tokens,
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
        turn: Turn,
        user_message: Message,
        system_prompt: str,
    ) -> tuple[
        Session,
        BuildResult,
        list[ToolSchema],
        int | None,
        list[Message],
        str | None,
        list[str] | None,
    ]:
        """Prepare context, tools, slot, and history for the inference loop."""
        await self._safe_transition(turn, TurnState.BUILDING_CONTEXT)
        all_tool_names = self._tools.list_names()
        allowed_tools = self._policy.filter_tools(session, all_tool_names, self._tools)
        history = await self._store.get_messages(session.id)
        await self._store.append_message(session.id, user_message)
        running_history: list[Message] = history + [user_message]

        effective_system_prompt = system_prompt
        if self._proposal_store is not None and not history:
            pending_count = await self._proposal_store.pending_count()
            if pending_count > 0:
                effective_system_prompt = (
                    f"You have {pending_count} pending reflection "
                    "proposal(s) from the last review. If the user "
                    "greets you or asks 'what's new', summarize the "
                    "top 3 and ask whether to accept/reject/defer. "
                    "Do not apply any proposal without an explicit "
                    f"accept.\n\n{system_prompt}"
                )

        style_prefix: str | None = None
        if (
            self._style_store is not None
            and self._style_config is not None
            and self._style_config.enabled
        ):
            from datetime import timedelta

            since = utcnow() - timedelta(days=self._style_config.lookback_days)
            turn_count = await self._style_store.count_turns_in_window(
                session.platform, session.platform_user, since
            )
            if turn_count >= self._style_config.min_turns_to_activate:
                metrics = await self._style_store.get_profile_dict(
                    session.platform, session.platform_user
                )
                style_prefix = format_style_prefix_from_data(metrics)

        tools = self._tools.meta_tool_schemas()
        self._builder.set_style_prefix(style_prefix)
        build_result = await self._builder.build(
            session=session,
            history=history,
            system_prompt=effective_system_prompt,
            tools=tools,
            new_user_message=user_message,
        )

        slot_id_to_use = session.slot_id
        if self._slot_manager is not None:
            assignment = await self._slot_manager.acquire(session)
            slot_id_to_use = assignment.slot_id
            refreshed = await self._store.get_session(session.id)
            if refreshed is not None:
                session = refreshed

        return (
            session, build_result, tools, slot_id_to_use,
            running_history, style_prefix, allowed_tools,
        )

    async def _handle_context_too_large(
        self,
        session: Session,
        turn: Turn,
        exc: ContextTooLargeError,
        user_message: Message,
        platform: Platform | None,
        platform_user: str | None,
        respond_callback: ResponseCallback,
        allowed_tools: list[str] | None,
        tool_chain: list[str],
        trace_record_id: str | None,
    ) -> str | None:
        """Handle ContextTooLargeError: handoff, transition, warning, record failure."""
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
            if platform is not None:
                await platform.send_system_warning(platform_user or "", warning_text)
            else:
                await respond_callback(f"⚠️ {warning_text}")
        return await self._record_failure_if_enabled(
            session, turn, exc, user_message, "context_too_large",
            allowed_tools, tool_chain, trace_record_id,
        )

    async def _handle_unexpected_error(
        self,
        session: Session,
        turn: Turn,
        error: Exception,
        user_message: Message,
        platform: Platform | None,
        platform_user: str | None,
        respond_callback: ResponseCallback,
        allowed_tools: list[str] | None,
        tool_chain: list[str],
        trace_record_id: str | None,
    ) -> str | None:
        """Handle unexpected errors: notify user, transition to FAILED, record failure."""
        if turn.state in (TurnState.DONE, TurnState.FAILED):
            logger.error(
                "Error after turn reached terminal state %s: %s",
                turn.state.value,
                error,
            )
            try:
                await respond_callback(f"Error delivering response: {error}")
            except Exception as notify_err:
                logger.warning(
                    "Failed to send post-terminal error notification: %s",
                    notify_err,
                )
        else:
            await self._safe_transition(turn, TurnState.FAILED)
            turn.error = str(error)
            await respond_callback(f"Error: {error}")
        return await self._record_failure_if_enabled(
            session, turn, error, user_message, "exception",
            allowed_tools, tool_chain, trace_record_id,
        )

    async def _run_inference_loop(
        self,
        session: Session,
        turn: Turn,
        build_result: BuildResult,
        tools: list[ToolSchema],
        slot_id_to_use: int | None,
        respond_callback: ResponseCallback,
        platform: Platform | None,
        platform_user: str | None,
        user_message: Message,
        allowed_tools: list[str] | None,
        style_prefix: str | None,
        system_prompt: str,
        running_history: list[Message],
        tool_chain: list[str],
        artifact_handles: list[str],
        total_prompt_tokens: int,
        total_completion_tokens: int,
        total_reasoning_tokens: int,
        delegated: bool,
    ) -> tuple[str, list[str], list[str], int, int, int, bool]:
        """Run the model inference loop: chat → tool dispatch → iterate."""
        content = ""
        while turn.iterations < self._max_iterations:
            await self._safe_transition(turn, TurnState.AWAITING_MODEL)
            await self._set_typing(platform, platform_user, True)

            turn.reasoning_budget = self._policy.reasoning_budget(session, turn.iterations)

            chat_response = await self._inference.chat(
                messages=build_result.messages,
                tools=tools,
                slot_id=slot_id_to_use,
                reasoning_budget=turn.reasoning_budget,
            )

            total_prompt_tokens += getattr(chat_response, "prompt_tokens", 0) or 0
            total_completion_tokens += getattr(chat_response, "completion_tokens", 0) or 0

            assistant_msg = Message(
                role="assistant",
                content=chat_response.content,
                tool_calls=chat_response.tool_calls,
                reasoning_content=chat_response.reasoning_content,
                created_at=utcnow(),
            )
            await self._store.append_message(session.id, assistant_msg)

            if chat_response.finish_reason == "tool_calls":
                await self._safe_transition(turn, TurnState.EXECUTING_TOOLS)

                tool_names = [tc.name for tc in chat_response.tool_calls]
                tool_chain.extend(tool_names)
                logger.debug("Executing tools: %s", ", ".join(tool_names))
                await self._set_typing(platform, platform_user, True)

                task_desc = (user_message.content or "").strip()
                use_policy_delegation = (
                    "delegate_task" in self._tools.list_names()
                    and self._policy.should_delegate(
                        session,
                        task_desc,
                        turn.tool_calls_made,
                        len(chat_response.tool_calls),
                    )
                )
                delegated = use_policy_delegation

                if use_policy_delegation:
                    await self._safe_transition(turn, TurnState.AWAITING_SUBAGENT)
                    tool_results, handles = await self._execute_policy_delegation(
                        user_message, chat_response.tool_calls
                    )
                    artifact_handles.extend(handles)
                    await self._safe_transition(turn, TurnState.EXECUTING_TOOLS)
                else:
                    tool_results, handles = await self._execute_tool_calls(
                        session, chat_response.tool_calls, allowed_tools
                    )
                    artifact_handles.extend(handles)

                for result_msg in tool_results:
                    await self._store.append_message(session.id, result_msg)

                await self._safe_transition(turn, TurnState.BUILDING_CONTEXT)

                running_history.append(assistant_msg)
                running_history.extend(tool_results)
                self._builder.set_style_prefix(style_prefix)
                build_result = await self._builder.build(
                    session=session,
                    history=running_history,
                    system_prompt=system_prompt,
                    tools=tools,
                    new_user_message=None,
                )

                turn.tool_calls_made += len(chat_response.tool_calls)
                turn.iterations += 1
                continue

            elif chat_response.finish_reason in ("stop", "length"):
                content = chat_response.content or ""
                if not content.strip() and not chat_response.tool_calls:
                    raise EmptyResponseError(
                        f"Model returned finish_reason={chat_response.finish_reason!r} "
                        f"with empty content and no tool calls"
                    )

                await self._set_typing(platform, platform_user, False)

                await self._safe_transition(turn, TurnState.DONE)
                turn.final_response = content
                await respond_callback(content)
                break

            else:
                decision = self._policy.retry_after_error(
                    Exception(f"Unexpected finish_reason: {chat_response.finish_reason}"),
                    turn.iterations,
                )
                if decision.action == RetryAction.FAIL:
                    raise PolicyFailureError(decision.reason)
                await self._safe_transition(turn, TurnState.RETRYING)
                turn.iterations += 1
        else:
            raise MaxIterationsError(self._max_iterations, turn.iterations)

        return (
            content,
            tool_chain,
            artifact_handles,
            total_prompt_tokens,
            total_completion_tokens,
            total_reasoning_tokens,
            delegated,
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
        session: Session,
        turn: Turn,
        user_message: Message,
        turn_start_time: Any,
        tool_chain: list[str],
        delegated: bool,
        artifact_handles: list[str],
        trace_record_id: str | None,
        total_prompt_tokens: int,
        total_completion_tokens: int,
        total_reasoning_tokens: int,
    ) -> None:
        """Finalize turn: save slot, update turn, record trace, set artifact handles."""
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

                raw_summary = user_message.content or ""
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
                    tools_called=tool_chain,
                    tool_call_count=len(tool_chain),
                    delegated=delegated,
                    outcome=outcome,
                    artifact_handles=artifact_handles,
                    prompt_tokens=total_prompt_tokens if total_prompt_tokens > 0 else None,
                    completion_tokens=(
                        total_completion_tokens if total_completion_tokens > 0 else None
                    ),
                    reasoning_tokens=total_reasoning_tokens if total_reasoning_tokens > 0 else None,
                    total_duration_ms=total_duration_ms,
                )
                await self._trace_store.record(trace)
            except Exception as trace_err:  # noqa: BLE001
                logger.error("Failed to record trace: %s", trace_err)

        turn.artifact_handles = list(artifact_handles)

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

    def _scan_tool_result(self, result: ToolCallResult) -> ToolCallResult:
        """Run injection scanner over a tool result, annotating if triggered."""
        if self._injection_scanner is None or not result.content:
            return result
        scan = self._injection_scanner.scan(result.content)
        if scan.triggered:
            result.content = self._injection_scanner.wrap(result.content, scan.reasons)
        return result

    async def _execute_tool_calls(
        self, session: Session, tool_calls: list[ToolCall], allowed_tools: list[str] | None = None
    ) -> tuple[list[Message], list[str]]:
        """Execute tool calls and return result messages and artifact handles.

        Tools marked ``ordering="serial"`` or requiring confirmation run
        sequentially; everything else is dispatched concurrently via
        :func:`asyncio.gather` to avoid stacking latencies.
        """
        result_messages: list[Message] = []
        artifact_handles: list[str] = []

        # Partition by dispatch mode. Tools requiring confirmation or marked
        # ordering="serial" run sequentially; everything else gathers concurrently.
        serial_indices: list[int] = []
        concurrent_indices: list[int] = []
        for i, tc in enumerate(tool_calls):
            try:
                meta = self._tools.describe(tc.name)
                is_serial = meta.requires_confirmation or meta.ordering == "serial"
            except ToolNotFoundError:
                is_serial = False
            if is_serial:
                serial_indices.append(i)
            else:
                concurrent_indices.append(i)

        # Run concurrent tools in parallel
        concurrent_results: dict[int, ToolCallResult] = {}
        if concurrent_indices:

            async def _run_one(idx: int) -> tuple[int, ToolCallResult]:
                tc = tool_calls[idx]
                result = await self._dispatch_tool_call(session, tc, allowed_tools)
                return idx, result

            for idx, result in await asyncio.gather(
                *[_run_one(i) for i in concurrent_indices]
            ):
                concurrent_results[idx] = result

        # Run serial tools sequentially
        serial_results: dict[int, ToolCallResult] = {}
        for idx in serial_indices:
            tc = tool_calls[idx]
            result = await self._dispatch_tool_call(session, tc, allowed_tools)
            serial_results[idx] = result

        # Reassemble in original emission order for trace consistency
        for i, tc in enumerate(tool_calls):
            result = concurrent_results[i] if i in concurrent_results else serial_results[i]
            result = self._scan_tool_result(result)
            if result.artifact_handle:
                artifact_handles.append(result.artifact_handle)

            msg = Message(
                role="tool",
                content=result.content,
                tool_call_id=tc.id,
                created_at=utcnow(),
            )
            result_messages.append(msg)

        return result_messages, artifact_handles

    async def _execute_policy_delegation(
        self,
        user_message: Message,
        tool_calls: list[ToolCall],
    ) -> tuple[list[Message], list[str]]:
        """Run delegate_task once; map output to one message per model tool_call_id."""
        task = (user_message.content or "").strip() or "(no user text)"
        lines = [f"{tc.name} {json.dumps(tc.arguments or {})}" for tc in tool_calls]
        context = "\n".join(lines)

        result = await self._tools.call(
            "delegate_task",
            {"task": task, "context": context},
        )
        result = self._scan_tool_result(result)
        body = result.content
        if result.status != "ok":
            body = f"[delegation error] {body}"

        artifact_handles: list[str] = []
        if result.artifact_handle:
            artifact_handles.append(result.artifact_handle)

        messages: list[Message] = []
        for i, tc in enumerate(tool_calls):
            if i == 0:
                content = body
            else:
                content = f"(Same policy delegation as tool_call_id={tool_calls[0].id}.)\n{body}"
            messages.append(
                Message(
                    role="tool",
                    content=content,
                    tool_call_id=tc.id,
                    created_at=utcnow(),
                )
            )
        return messages, artifact_handles

    async def _check_confirmation(
        self,
        *,
        tool: ToolMetadata,
        tool_name: str,
        arguments: dict[str, Any],
        session: Session,
    ) -> ToolCallResult | None:
        """Return None if approved (or if the tool does not require confirmation),
        or a ToolCallResult(error=...) if denied / unable to confirm."""
        if not tool.requires_confirmation:
            return None

        if self._policy.auto_approve(tool_name, session):
            # Trust profile auto-approves this tool for this session context.
            return None

        if self._confirm_callback is None:
            return ToolCallResult.error(
                (
                    f"Tool '{tool_name}' requires user confirmation but no "
                    "confirm_callback is configured and the trust profile does "
                    "not auto-approve it. Add the tool to "
                    "TrustConfig.auto_approve_tools, or run via a platform that "
                    "supports confirmation (CLI)."
                ),
            )

        confirmed = await self._confirm_callback(tool_name, arguments)
        if not confirmed:
            return ToolCallResult.error(
                "Tool execution was cancelled by user.",
            )

        return None

    async def _dispatch_tool_call(
        self, session: Session, tc: ToolCall, allowed_tools: list[str] | None = None
    ) -> ToolCallResult:
        """Dispatch a single tool call, handling meta-tools and direct tool calls.

        Args:
            tc: The tool call to dispatch
            allowed_tools: Optional list of allowed tool names for filtering
        """
        # Check if tool is allowed (meta-tools are always available)
        if (
            allowed_tools is not None
            and tc.name not in ("call_tool", "list_tools")
            and tc.name not in allowed_tools
        ):
            return ToolCallResult.error(
                f"Tool '{tc.name}' is not available in this session context.",
            )

        # Handle meta-tools
        if tc.name == "list_tools":
            tag = tc.arguments.get("tag") if tc.arguments else None
            content = await self._tools.meta_list_tools(tag, allowed_names=allowed_tools)
            return ToolCallResult(
                status="ok",
                content=content,
                artifact_handle=None,
                truncated=False,
            )

        if tc.name == "call_tool":
            name = tc.arguments.get("name") if tc.arguments else None
            arguments = tc.arguments.get("arguments") if tc.arguments else {}
            if not isinstance(arguments, dict):
                return ToolCallResult.error(
                    f"Malformed arguments for tool '{tc.name}'.",
                )
            if not name:
                return ToolCallResult.error(
                    "Missing 'name' argument for call_tool",
                )

            # Check if inner tool is allowed
            if allowed_tools is not None and name not in allowed_tools:
                return ToolCallResult.error(
                    f"Tool '{name}' is not available in this session context.",
                )

            # Confirmation enforcement: check the INNER tool's metadata before dispatch
            try:
                inner_meta = self._tools.describe(name)
            except ToolNotFoundError:
                return ToolCallResult.error(
                    f"Tool not found: {name}",
                )

            confirm_result = await self._check_confirmation(
                tool=inner_meta, tool_name=name, arguments=arguments, session=session
            )
            if confirm_result is not None:
                return confirm_result

            return await self._tools.meta_call_tool(name, arguments)

        # Direct tool call (non-meta-tool)
        # Check if tool exists and handle confirmation
        try:
            meta = self._tools.describe(tc.name)
        except ToolNotFoundError:
            return ToolCallResult.error(
                f"Unknown tool: {tc.name}",
            )

        confirm_result = await self._check_confirmation(
            tool=meta, tool_name=tc.name, arguments=tc.arguments or {}, session=session
        )
        if confirm_result is not None:
            return confirm_result

        result = await self._tools.call(tc.name, tc.arguments or {})
        return self._scan_tool_result(result)
