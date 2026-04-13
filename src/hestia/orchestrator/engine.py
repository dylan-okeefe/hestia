"""Orchestrator engine for managing turn execution."""

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from hestia.context.builder import ContextBuilder
from hestia.core.inference import InferenceClient
from hestia.core.types import Message, Session, ToolCall
from hestia.errors import EmptyResponseError, IllegalTransitionError, classify_error
from hestia.inference.slot_manager import SlotManager
from hestia.orchestrator.transitions import assert_transition
from hestia.orchestrator.types import Turn, TurnState, TurnTransition
from hestia.persistence.sessions import SessionStore
from hestia.platforms.base import Platform
from hestia.policy.engine import PolicyEngine, RetryAction
from hestia.tools.builtin import current_session_id
from hestia.tools.registry import ToolRegistry
from hestia.tools.types import ToolCallResult

if TYPE_CHECKING:
    from hestia.persistence.failure_store import FailureStore

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

    async def _update_status(
        self,
        platform: Platform | None,
        platform_user: str | None,
        status_msg_id: str | None,
        text: str,
    ) -> None:
        """Update the status message if a platform is available."""
        if platform is not None and status_msg_id is not None and platform_user is not None:
            try:
                await platform.edit_message(platform_user, status_msg_id, text)
            except Exception as e:
                logger.warning("Failed to update status: %s", e)

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

            # Send initial status message if platform is available
            status_msg_id: str | None = None
            if platform is not None and platform_user is not None:
                try:
                    status_msg_id = await platform.send_message(platform_user, "Thinking...")
                except Exception as e:
                    logger.warning("Failed to send status message: %s", e)

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
                    await self._update_status(platform, platform_user, status_msg_id, "Thinking...")

                    chat_response = await self._inference.chat(
                        messages=build_result.messages,
                        tools=tools,
                        slot_id=slot_id_to_use,
                        reasoning_budget=2048,
                    )

                    # Append assistant message to history
                    assistant_msg = Message(
                        role="assistant",
                        content=chat_response.content,
                        tool_calls=chat_response.tool_calls,
                        reasoning_content=chat_response.reasoning_content,
                        created_at=datetime.now(),
                    )
                    await self._store.append_message(session.id, assistant_msg)

                    if chat_response.finish_reason == "tool_calls":
                        await self._transition(turn, TurnState.EXECUTING_TOOLS)

                        # Update status with tool names
                        tool_names = [tc.name for tc in chat_response.tool_calls]
                        tool_chain.extend(tool_names)
                        status_text = f"Running {', '.join(tool_names)}..."
                        await self._update_status(
                            platform, platform_user, status_msg_id, status_text
                        )

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
                        await self._transition(turn, TurnState.DONE)
                        turn.final_response = content
                        await respond_callback(content)

                        # Save slot checkpoint after successful turn (don't fail turn if save fails)
                        if self._slot_manager is not None:
                            try:
                                await self._slot_manager.save(session)
                            except Exception as e:
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
            except Exception as e:
                await self._transition(turn, TurnState.FAILED)
                turn.error = str(e)
                await respond_callback(f"Error: {e}")

                # Record failure bundle if store is configured
                if self._failure_store is not None:
                    try:
                        from hestia.persistence.failure_store import FailureBundle

                        failure_class, severity = classify_error(e)
                        bundle = FailureBundle(
                            id=str(uuid.uuid4()),
                            session_id=session.id,
                            turn_id=turn.id,
                            failure_class=failure_class.value,
                            severity=severity,
                            error_message=str(e),
                            tool_chain=json.dumps(tool_chain),
                            created_at=datetime.now(),
                        )
                        await self._failure_store.record(bundle)
                    except Exception as record_err:
                        logger.warning("Failed to record failure bundle: %s", record_err)

            finally:
                turn.completed_at = datetime.now()
                await self._store.update_turn(turn)

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
            started_at=datetime.now(),
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
            at=datetime.now(),
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
                created_at=datetime.now(),
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
                    created_at=datetime.now(),
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
        # Check if tool is allowed (for call_tool, we check the inner tool later)
        if allowed_tools is not None and tc.name != "call_tool":
            if tc.name not in allowed_tools:
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
            except Exception:
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
        except Exception:
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
