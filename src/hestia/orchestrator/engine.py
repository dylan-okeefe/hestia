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
    EmptyResponseError,
    IllegalTransitionError,
    PersistenceError,
    PlatformError,
    classify_error,
)
from hestia.inference.slot_manager import SlotManager
from hestia.orchestrator.transitions import assert_transition
from hestia.orchestrator.types import Turn, TurnState, TurnTransition
from hestia.persistence.sessions import SessionStore
from hestia.platforms.base import Platform
from hestia.policy.engine import PolicyEngine, RetryAction
from hestia.tools.builtin import current_session_id
from hestia.tools.registry import ToolNotFoundError, ToolRegistry
from hestia.tools.types import ToolCallResult

if TYPE_CHECKING:
    from hestia.persistence.failure_store import FailureStore
    from hestia.persistence.trace_store import TraceStore

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
        """Process a single user turn through the state machine.

        Args:
            session: Current session
            user_message: The user's message
            respond_callback: Async callback to send responses to user
            system_prompt: System prompt for the model
            platform: Optional platform adapter for status updates
            platform_user: Optional platform user ID for status updates

        Returns:
            Completed Turn with full history
        """
        # Set session context for tools that need to know the current session
        session_token = current_session_id.set(session.id)

        try:
            turn = self._create_turn(session.id, user_message)
            await self._persist_turn(turn)
            tool_chain: list[str] = []  # Initialize before inner try block

            await self._set_typing(platform, platform_user, True)

            # Track timing and token usage for trace
            turn_start_time = utcnow()
            total_prompt_tokens = 0
            total_completion_tokens = 0
            total_reasoning_tokens = 0
            artifact_handles: list[str] = []

            trace_record_id: str | None = None

            allowed_tools: list[str] | None = None
            policy_snapshot: str = json.dumps({"error": "policy not initialized"})
            slot_snapshot: str = json.dumps({"error": "slot not initialized"})

            try:
                # Start processing
                await self._transition(turn, TurnState.BUILDING_CONTEXT)

                # Compute allowed tools based on session context
                all_tool_names = self._tools.list_names()
                allowed_tools = self._policy.filter_tools(session, all_tool_names, self._tools)

                # Load prior history (does not include the current user message)
                history = await self._store.get_messages(session.id)

                # Persist the new user message (now it's in the store for future turns)
                await self._store.append_message(session.id, user_message)

                # Build context
                tools = self._tools.meta_tool_schemas()
                build_result = await self._builder.build(
                    session=session,
                    history=history,
                    system_prompt=system_prompt,
                    tools=tools,
                    new_user_message=user_message,
                )

                # Acquire slot for this turn (if SlotManager is configured)
                slot_id_to_use: int | None
                if self._slot_manager is not None:
                    assignment = await self._slot_manager.acquire(session)
                    slot_id_to_use = assignment.slot_id
                    # Refetch session in case slot_id/temperature changed
                    refreshed = await self._store.get_session(session.id)
                    if refreshed is not None:
                        session = refreshed
                else:
                    slot_id_to_use = session.slot_id

                # Main loop: model -> tools -> model -> ...
                while turn.iterations < self._max_iterations:
                    await self._transition(turn, TurnState.AWAITING_MODEL)
                    await self._set_typing(platform, platform_user, True)

                    # Get reasoning budget from policy and update turn
                    turn.reasoning_budget = self._policy.reasoning_budget(session, turn.iterations)

                    chat_response = await self._inference.chat(
                        messages=build_result.messages,
                        tools=tools,
                        slot_id=slot_id_to_use,
                        reasoning_budget=turn.reasoning_budget,
                    )

                    # Accumulate token usage for trace
                    total_prompt_tokens += getattr(chat_response, "prompt_tokens", 0) or 0
                    total_completion_tokens += getattr(chat_response, "completion_tokens", 0) or 0

                    # Append assistant message to history
                    assistant_msg = Message(
                        role="assistant",
                        content=chat_response.content,
                        tool_calls=chat_response.tool_calls,
                        reasoning_content=chat_response.reasoning_content,
                        created_at=utcnow(),
                    )
                    await self._store.append_message(session.id, assistant_msg)

                    if chat_response.finish_reason == "tool_calls":
                        await self._transition(turn, TurnState.EXECUTING_TOOLS)

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
                            await self._transition(turn, TurnState.AWAITING_SUBAGENT)
                            tool_results = await self._execute_policy_delegation(
                                user_message, chat_response.tool_calls
                            )
                            await self._transition(turn, TurnState.EXECUTING_TOOLS)
                        else:
                            tool_results = await self._execute_tool_calls(
                                session.id, chat_response.tool_calls, allowed_tools
                            )

                        # Add tool results to history
                        for result_msg in tool_results:
                            await self._store.append_message(session.id, result_msg)

                        # Transition back to building context for next model call
                        await self._transition(turn, TurnState.BUILDING_CONTEXT)

                        # Rebuild context with new history
                        history = await self._store.get_messages(session.id)
                        build_result = await self._builder.build(
                            session=session,
                            history=history,
                            system_prompt=system_prompt,
                            tools=tools,
                            new_user_message=None,  # Continuing turn, no new user message
                        )

                        turn.tool_calls_made += len(chat_response.tool_calls)
                        turn.iterations += 1
                        continue  # Loop back for another model call

                    elif chat_response.finish_reason in ("stop", "length"):
                        content = chat_response.content or ""
                        if not content.strip() and not chat_response.tool_calls:
                            raise EmptyResponseError(
                                f"Model returned finish_reason={chat_response.finish_reason!r} "
                                f"with empty content and no tool calls"
                            )

                        await self._set_typing(platform, platform_user, False)

                        await self._transition(turn, TurnState.DONE)
                        turn.final_response = content
                        await respond_callback(content)

                        # Collect artifact handles from successful tool results
                        for msg in await self._store.get_messages(session.id):
                            if (
                                msg.role == "tool"
                                and msg.content
                                and "artifact://" in msg.content
                            ):
                                import re

                                handles = re.findall(
                                    r"artifact://([a-zA-Z0-9_-]+)", msg.content
                                )
                                artifact_handles.extend(handles)

                        # Save slot checkpoint after successful turn (don't fail turn if save fails)
                        if self._slot_manager is not None:
                            try:
                                await self._slot_manager.save(session)
                            except (OSError, PersistenceError) as e:
                                logger.warning(
                                    "Failed to save slot for session %s: %s", session.id, e
                                )

                        break

                    else:
                        # Unexpected finish reason - retry
                        decision = self._policy.retry_after_error(
                            Exception(f"Unexpected finish_reason: {chat_response.finish_reason}"),
                            turn.iterations,
                        )
                        if decision.action == RetryAction.FAIL:
                            raise Exception(decision.reason)
                        await self._transition(turn, TurnState.RETRYING)
                        turn.iterations += 1

                else:
                    # Max iterations reached
                    raise Exception(f"Max iterations ({self._max_iterations}) exceeded")

            except IllegalTransitionError:
                raise  # Re-raise state machine errors
            except Exception as e:  # Outermost boundary — intentionally broad
                await self._set_typing(platform, platform_user, False)

                if turn.state in (TurnState.DONE, TurnState.FAILED):
                    # A1 minimal fix: delivery or post-DONE errors must not
                    # attempt an illegal transition from a terminal state.
                    logger.error(
                        "Error after turn reached terminal state %s: %s",
                        turn.state.value,
                        e,
                    )
                    try:
                        await respond_callback(f"Error delivering response: {e}")
                    except Exception as notify_err:  # noqa: BLE001
                        logger.warning(
                            "Failed to send post-terminal error notification: %s",
                            notify_err,
                        )
                else:
                    await self._transition(turn, TurnState.FAILED)
                    turn.error = str(e)
                    await respond_callback(f"Error: {e}")

                    # Record failure bundle if store is configured
                if self._failure_store is not None:
                    try:
                        from hestia.persistence.failure_store import FailureBundle

                        failure_class, severity = classify_error(e)

                        # Build request summary (truncate with ... if > 200 chars)
                        raw_summary = user_message.content or ""
                        if len(raw_summary) > 200:
                            user_input_summary = raw_summary[:200] + "..."
                        else:
                            user_input_summary = raw_summary

                        # Build policy snapshot using policy engine methods
                        reasoning_budget = turn.reasoning_budget
                        if reasoning_budget is None:
                            reasoning_budget = self._policy.reasoning_budget(
                                session, turn.iterations
                            )
                        policy_snapshot = json.dumps(
                            {
                                "reasoning_budget": reasoning_budget,
                                "turn_token_budget": self._policy.turn_token_budget(session),
                                "tool_filter_active": allowed_tools is not None,
                            },
                            default=str,
                        )

                        # Build slot snapshot
                        try:
                            temp_value = None
                            if hasattr(session, "temperature") and session.temperature is not None:
                                if hasattr(session.temperature, "value"):
                                    temp_value = session.temperature.value
                                else:
                                    temp_value = str(session.temperature)
                            slot_snapshot = json.dumps(
                                {
                                    "slot_id": session.slot_id,
                                    "temperature": temp_value,
                                    "slot_saved_path": getattr(session, "slot_saved_path", None),
                                },
                                default=str,
                            )
                        except (TypeError, AttributeError):
                            slot_snapshot = json.dumps(
                                {"error": "slot snapshot serialization failed"}
                            )

                        # Link trace ID if trace store is configured
                        if self._trace_store is not None:
                            trace_record_id = str(uuid.uuid4())

                        bundle = FailureBundle(
                            id=str(uuid.uuid4()),
                            session_id=session.id,
                            turn_id=turn.id,
                            failure_class=failure_class.value,
                            severity=severity,
                            error_message=str(e),
                            tool_chain=json.dumps(tool_chain),
                            created_at=utcnow(),
                            request_summary=user_input_summary,
                            policy_snapshot=policy_snapshot,
                            slot_snapshot=slot_snapshot,
                            trace_id=trace_record_id,
                        )
                        await self._failure_store.record(bundle)
                    except Exception as record_err:  # noqa: BLE001
                        # Outermost boundary — intentionally broad to avoid masking original error
                        logger.error("Failed to record failure bundle: %s", record_err)

            finally:
                # Calculate timing
                turn_end_time = utcnow()
                total_duration_ms = int((turn_end_time - turn_start_time).total_seconds() * 1000)

                turn.completed_at = turn_end_time
                await self._store.update_turn(turn)

                # Record trace (narrow try/except - never mask original exception)
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
                            delegated=locals().get("delegated", False),
                            outcome=outcome,
                            artifact_handles=artifact_handles,
                            prompt_tokens=total_prompt_tokens if total_prompt_tokens > 0 else None,
                            completion_tokens=(
                                total_completion_tokens if total_completion_tokens > 0 else None
                            ),
                            reasoning_tokens=(
                                total_reasoning_tokens if total_reasoning_tokens > 0 else None
                            ),
                            total_duration_ms=total_duration_ms,
                        )
                        await self._trace_store.record(trace)
                    except Exception as trace_err:  # noqa: BLE001
                        # Outermost boundary — intentionally broad to avoid masking original error
                        logger.error("Failed to record trace: %s", trace_err)

            return turn

        finally:
            # Clear session context when turn processing completes
            current_session_id.reset(session_token)

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

    async def _execute_tool_calls(
        self, session_id: str, tool_calls: list[ToolCall], allowed_tools: list[str] | None = None
    ) -> list[Message]:
        """Execute tool calls and return result messages."""
        result_messages = []

        for tc in tool_calls:
            result = await self._dispatch_tool_call(tc, allowed_tools)

            msg = Message(
                role="tool",
                content=result.content,
                tool_call_id=tc.id,
                created_at=utcnow(),
            )
            result_messages.append(msg)

        return result_messages

    async def _execute_policy_delegation(
        self,
        user_message: Message,
        tool_calls: list[ToolCall],
    ) -> list[Message]:
        """Run delegate_task once; map output to one message per model tool_call_id."""
        task = (user_message.content or "").strip() or "(no user text)"
        lines = [f"{tc.name} {json.dumps(tc.arguments or {})}" for tc in tool_calls]
        context = "\n".join(lines)

        result = await self._tools.call(
            "delegate_task",
            {"task": task, "context": context},
        )
        body = result.content
        if result.status != "ok":
            body = f"[delegation error] {body}"

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
        return messages

    async def _dispatch_tool_call(
        self, tc: ToolCall, allowed_tools: list[str] | None = None
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
            return ToolCallResult(
                status="error",
                content=f"Tool '{tc.name}' is not available in this session context.",
                artifact_handle=None,
                truncated=False,
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
            if not name:
                return ToolCallResult(
                    status="error",
                    content="Missing 'name' argument for call_tool",
                    artifact_handle=None,
                    truncated=False,
                )

            # Check if inner tool is allowed
            if allowed_tools is not None and name not in allowed_tools:
                return ToolCallResult(
                    status="error",
                    content=f"Tool '{name}' is not available in this session context.",
                    artifact_handle=None,
                    truncated=False,
                )

            # Confirmation enforcement: check the INNER tool's metadata before dispatch
            try:
                inner_meta = self._tools.describe(name)
            except ToolNotFoundError:
                return ToolCallResult(
                    status="error",
                    content=f"Tool not found: {name}",
                    artifact_handle=None,
                    truncated=False,
                )

            if inner_meta.requires_confirmation:
                if self._confirm_callback is None:
                    return ToolCallResult(
                        status="error",
                        content=(
                            f"Tool '{name}' requires user confirmation but no "
                            "confirm_callback is configured on this orchestrator."
                        ),
                        artifact_handle=None,
                        truncated=False,
                    )
                confirmed = await self._confirm_callback(name, arguments)
                if not confirmed:
                    return ToolCallResult(
                        status="error",
                        content="Tool execution was cancelled by user.",
                        artifact_handle=None,
                        truncated=False,
                    )

            return await self._tools.meta_call_tool(name, arguments)

        # Direct tool call (non-meta-tool)
        # Check if tool exists and handle confirmation
        try:
            meta = self._tools.describe(tc.name)
        except ToolNotFoundError:
            return ToolCallResult(
                status="error",
                content=f"Unknown tool: {tc.name}",
                artifact_handle=None,
                truncated=False,
            )

        if meta.requires_confirmation:
            if self._confirm_callback is None:
                return ToolCallResult(
                    status="error",
                    content=(
                        f"Tool '{tc.name}' requires user confirmation but no "
                        "confirm_callback is configured on this orchestrator."
                    ),
                    artifact_handle=None,
                    truncated=False,
                )
            confirmed = await self._confirm_callback(tc.name, tc.arguments or {})
            if not confirmed:
                return ToolCallResult(
                    status="error",
                    content="Tool execution was cancelled by user.",
                    artifact_handle=None,
                    truncated=False,
                )

        return await self._tools.call(tc.name, tc.arguments or {})
