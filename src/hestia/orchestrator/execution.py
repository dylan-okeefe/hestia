"""Turn execution phase: model inference, tool dispatch, confirmation gating."""

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from hestia.core.clock import utcnow
from hestia.core.inference import InferenceClient, _extract_tool_calls_from_text
from hestia.core.json_repair import repair_json
from hestia.core.types import ChatResponse, Message, Session, ToolCall
from hestia.diagnostics import regression_collector
from hestia.errors import (
    EmptyResponseError,
    MaxIterationsError,
    PolicyFailureError,
    ThinkingBudgetExceededError,
)
from hestia.orchestrator.quality import Correction, DegeneratePattern, classify_turn
from hestia.orchestrator.types import TransitionCallback, Turn, TurnContext, TurnState
from hestia.policy.engine import PolicyEngine, RetryAction
from hestia.security import InjectionScanner
from hestia.tools.metadata import ToolMetadata
from hestia.tools.registry import ToolNotFoundError, ToolRegistry
from hestia.tools.result_classifier import ToolResultCategory, classify_tool_result
from hestia.tools.types import ToolCallResult

if TYPE_CHECKING:
    from hestia.events.bus import EventBus

if TYPE_CHECKING:
    from hestia.context.builder import ContextBuilder
    from hestia.persistence.sessions import SessionStore

logger = logging.getLogger(__name__)

ConfirmCallback = Callable[[str, dict[str, Any]], Awaitable[bool]]
TypingCallback = Callable[[bool], Awaitable[None]]

# Inter-chunk timeout: once the model has started emitting tokens, if no chunk
# arrives for this long we assume the stream is dead and finish.  Tool-call
# argument JSON can be large, so this needs to be generous enough for the
# server to finish emitting a complete chunk.
_STREAM_INACTIVITY_TIMEOUT = 60.0

# First-chunk timeout: prompt processing for long contexts can take tens of
# seconds without emitting any tokens.  We allow up to two minutes for the
# first chunk before giving up, while keeping the inter-chunk timeout tight.
_STREAM_FIRST_CHUNK_TIMEOUT = 120.0

# Timeout escalation schedule for repeated TIMEOUT retries (seconds).
_TIMEOUT_ESCALATION_SCHEDULE = (15.0, 30.0, 60.0)
_MAX_PER_ATTEMPT_TIMEOUT = 90.0
_DEFAULT_URL_TIME_BUDGET = 120.0


_ToolCallKey = tuple[str, tuple[tuple[str, Any], ...]]


def _tool_call_key(tc: ToolCall) -> _ToolCallKey:
    """Return a stable, comparable representation of a tool call.

    Argument values may be lists or dicts (e.g. describe_tool(names=[...])),
    so they are recursively frozen into hashable tuples before sorting.
    """

    def _freeze(value: Any) -> Any:
        if isinstance(value, dict):
            return tuple(sorted((k, _freeze(v)) for k, v in value.items()))
        if isinstance(value, list):
            return tuple(_freeze(v) for v in value)
        return value

    args = tuple(sorted((k, _freeze(v)) for k, v in (tc.arguments or {}).items()))
    return (tc.name, args)


def _extract_url_from_tool_call(tc: ToolCall) -> str | None:
    """Return the URL argument of a tool call if present."""
    if not tc.arguments:
        return None
    for key, value in tc.arguments.items():
        if key.lower() == "url" and isinstance(value, str):
            return value
    return None


def _format_retry_exhausted_message(
    tool_name: str,
    category: ToolResultCategory,
    retry_count: int,
    url: str | None,
    *,
    budget_exhausted: bool = False,
) -> str:
    """Format the block message when retries are exhausted."""
    if url:
        target = url
        disabled = "This URL is now DISABLED for the rest of this turn"
    else:
        target = "these arguments"
        disabled = "This tool is now DISABLED for the rest of this turn"
    category_phrase = category.name.lower().replace("_", " ")
    budget_note = " (total URL time budget exhausted)" if budget_exhausted else ""
    return (
        f"🛑 {tool_name} {category_phrase} {retry_count} time(s) for {target}. "
        f"{disabled}{budget_note}. "
        "Try http_get, web_search, or grep the cached artifact instead."
    )


def _escalated_timeout_seconds(tc: ToolCall, retry_count: int) -> float:
    """Return the escalated timeout_seconds for a TIMEOUT retry."""
    current = tc.arguments.get("timeout_seconds") if tc.arguments else None
    base = float(current) if isinstance(current, (int, float)) else 0.0
    schedule_value = _TIMEOUT_ESCALATION_SCHEDULE[
        min(retry_count, len(_TIMEOUT_ESCALATION_SCHEDULE) - 1)
    ]
    return min(max(base, schedule_value), _MAX_PER_ATTEMPT_TIMEOUT)


def _tool_call_with_timeout(tc: ToolCall, timeout: float) -> ToolCall:
    """Return a copy of ``tc`` with ``timeout_seconds`` set to ``timeout``."""
    new_arguments = dict(tc.arguments or {})
    new_arguments["timeout_seconds"] = timeout
    return ToolCall(id=tc.id, name=tc.name, arguments=new_arguments)


def _consume_url_budget(
    ctx: TurnContext,
    url: str | None,
    proposed_timeout: float,
) -> bool:
    """Return True when the URL has enough budget and reserve ``proposed_timeout``.

    A ``None`` URL always succeeds (no budget tracking for non-URL calls).
    """
    if url is None:
        return True
    remaining = ctx._url_time_budgets.get(url, _DEFAULT_URL_TIME_BUDGET)
    if proposed_timeout > remaining:
        return False
    ctx._url_time_budgets[url] = remaining - proposed_timeout
    return True


def _normalize_tool_arguments(arguments: Any) -> dict[str, Any]:
    """Coerce tool-call arguments to a dict.

    Small/reasoning models sometimes emit arguments as a string, list, or other
    non-dict value (especially after JSON repair or when streaming deltas are
    truncated).  Treating those as an empty dict lets the turn continue with a
    useful error rather than raising an AttributeError downstream.
    """
    if isinstance(arguments, dict):
        return arguments
    if arguments is None or arguments == "":
        return {}
    logger.warning(
        "Tool-call arguments are %s, not dict; coercing to {}",
        type(arguments).__name__,
    )
    return {}


def _is_retryable_tool_result(content: str) -> bool:
    """True when a tool result looks like a transient failure worth retrying."""
    return classify_tool_result(content) in (
        ToolResultCategory.TIMEOUT,
        ToolResultCategory.TRANSIENT_OTHER,
    )


def _latest_tool_result_categories(
    history: list[Message],
) -> dict[str, ToolResultCategory]:
    """Return the latest result category for each tool_call_id."""
    latest_result: dict[str, str] = {}
    pending_ids: set[str] = set()
    for msg in history:
        if msg.role == "assistant" and msg.tool_calls:
            pending_ids.update(tc.id for tc in msg.tool_calls)
        elif (
            msg.role == "tool"
            and msg.tool_call_id
            and msg.tool_call_id in pending_ids
        ):
            latest_result[msg.tool_call_id] = msg.content or ""
            pending_ids.discard(msg.tool_call_id)
    return {
        tid: classify_tool_result(content)
        for tid, content in latest_result.items()
    }


class TurnExecution:
    """Runs the model inference loop and dispatches tool calls."""

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry,
        inference_client: InferenceClient,
        policy: PolicyEngine,
        context_builder: "ContextBuilder",
        session_store: "SessionStore",
        confirm_callback: ConfirmCallback | None = None,
        injection_scanner: InjectionScanner | None = None,
        max_iterations: int = 10,
        max_tool_calls_per_turn: int = 10,
        max_retries_for_failed_tool_call: int = 2,
        max_tokens: int = 1024,
        stream: bool = False,
        event_bus: "EventBus | None" = None,
    ) -> None:
        self._tools = tool_registry
        self._inference = inference_client
        self._policy = policy
        self._builder = context_builder
        self._store = session_store
        self._confirm_callback = confirm_callback
        self._injection_scanner = injection_scanner
        self._max_iterations = max_iterations
        self._max_tool_calls_per_turn = max_tool_calls_per_turn
        self._max_retries_for_failed_tool_call = max_retries_for_failed_tool_call
        self._max_tokens = max_tokens
        self._stream = stream
        self._event_bus = event_bus

        # Meta-tool dispatch table — adding a new meta-tool is one line.
        self._meta_tools: dict[
            str, Callable[[Session, ToolCall, list[str] | None], Awaitable[ToolCallResult]]
        ] = {
            "list_tools": self._meta_list_tools,
            "describe_tool": self._meta_describe_tool,
            "call_tool": self._meta_call_tool,
        }

    async def run(
        self,
        ctx: TurnContext,
        transition: TransitionCallback,
        set_typing: TypingCallback,
    ) -> str:
        """Run the model inference loop: chat → tool dispatch → iterate."""
        session = ctx.session
        turn = ctx.turn
        if ctx.build_result is None:
            raise RuntimeError("TurnContext not prepared before TurnExecution.run")

        content = ""
        while turn.iterations < self._max_iterations:
            await transition(turn, TurnState.AWAITING_MODEL, "")
            await set_typing(True)

            turn.reasoning_budget = self._policy.reasoning_budget(session, turn.iterations)
            if turn.thinking_aborted:
                turn.reasoning_budget = 0

            try:
                if ctx.stream_callback is not None and self._stream:
                    chat_response = await self._run_inference_streaming(ctx, turn)
                else:
                    chat_response = await self._inference.chat(
                        messages=ctx.build_result.messages,
                        tools=ctx.tools,
                        slot_id=ctx.slot_id,
                        reasoning_budget=turn.reasoning_budget,
                        max_tokens=self._max_tokens,
                    )
            except ThinkingBudgetExceededError:
                await transition(turn, TurnState.RETRYING, "")
                turn.thinking_aborted = True
                nudge = Message(
                    role="system",
                    content=(
                        "You have been thinking for a long time. "
                        "Stop deliberating and use your tools to complete the task."
                    ),
                    created_at=utcnow(),
                )
                await self._store.append_message(session.id, nudge)
                ctx.running_history.append(nudge)
                self._builder.set_style_prefix(ctx.style_prefix)
                ctx.build_result = await self._builder.build(
                    session=ctx.session,
                    history=ctx.running_history,
                    system_prompt=ctx.system_prompt,
                    tools=ctx.tools,
                    new_user_message=None,
                )
                turn.iterations += 1
                continue

            ctx.total_prompt_tokens += getattr(chat_response, "prompt_tokens", 0) or 0
            ctx.total_completion_tokens += getattr(chat_response, "completion_tokens", 0) or 0

            assistant_msg = Message(
                role="assistant",
                content=chat_response.content,
                tool_calls=chat_response.tool_calls,
                reasoning_content=chat_response.reasoning_content,
                created_at=utcnow(),
            )
            await self._store.append_message(session.id, assistant_msg)

            # Guardrail: model is reasoning extensively but not acting
            if (
                chat_response.reasoning_content
                and len(chat_response.reasoning_content) > 1500
                and not chat_response.tool_calls
                and not chat_response.content
            ):
                await ctx.respond_callback(
                    "🛑 You have been reasoning extensively but haven't emitted a tool call. "
                    "Please make a tool call now."
                )
                await transition(turn, TurnState.RETRYING, "")
                turn.iterations += 1
                continue

            if chat_response.finish_reason == "tool_calls":
                await self._handle_tool_calls(
                    ctx, turn, chat_response, transition, set_typing, assistant_msg
                )
                await self._classify_and_maybe_correct(
                    ctx, turn, assistant_msg, history_includes_current=True
                )
                continue

            elif chat_response.finish_reason in ("stop", "length"):
                content = chat_response.content or ""

                # Some models occasionally emit finish_reason="stop" alongside
                # tool_calls. If tool_calls are present, execute them and continue
                # the loop rather than treating the turn as done.
                if chat_response.tool_calls:
                    logger.debug(
                        "finish_reason=%s but tool_calls present (%d); routing to tool execution",
                        chat_response.finish_reason,
                        len(chat_response.tool_calls),
                    )
                    await self._handle_tool_calls(
                        ctx, turn, chat_response, transition, set_typing, assistant_msg
                    )
                    await self._classify_and_maybe_correct(
                        ctx, turn, assistant_msg, history_includes_current=True
                    )
                    continue

                if not content.strip():
                    # Empty response — retry via policy instead of failing immediately
                    if await self._classify_and_maybe_correct(
                        ctx, turn, assistant_msg, history_includes_current=False
                    ):
                        await transition(turn, TurnState.RETRYING, "")
                        turn.iterations += 1
                        continue
                    decision = self._policy.retry_after_error(
                        EmptyResponseError(
                            f"Model returned finish_reason={chat_response.finish_reason!r} "
                            f"with empty content and no tool calls"
                        ),
                        turn.iterations,
                    )
                    if decision.action == RetryAction.FAIL:
                        raise PolicyFailureError(decision.reason)
                    await transition(turn, TurnState.RETRYING, "")
                    turn.iterations += 1
                    continue

                if await self._classify_and_maybe_correct(
                    ctx, turn, assistant_msg, history_includes_current=False
                ):
                    await transition(turn, TurnState.RETRYING, "")
                    turn.iterations += 1
                    continue

                await set_typing(False)

                await transition(turn, TurnState.DONE, "")
                turn.final_response = content
                # Surface reasoning to user (does not affect stored message or prompt)
                if chat_response.reasoning_content:
                    reasoning_text = chat_response.reasoning_content[:2000]
                    if len(chat_response.reasoning_content) > 2000:
                        reasoning_text += "\n\n... (reasoning truncated)"
                    display = f"💭 {reasoning_text}\n\n━━━\n\n{content}"
                else:
                    display = content
                await ctx.respond_callback(display)
                break

            else:
                if await self._classify_and_maybe_correct(
                    ctx, turn, assistant_msg, history_includes_current=False
                ):
                    await transition(turn, TurnState.RETRYING, "")
                    turn.iterations += 1
                    continue
                decision = self._policy.retry_after_error(
                    Exception(f"Unexpected finish_reason: {chat_response.finish_reason}"),
                    turn.iterations,
                )
                if decision.action == RetryAction.FAIL:
                    raise PolicyFailureError(decision.reason)
                await transition(turn, TurnState.RETRYING, "")
                turn.iterations += 1
        else:
            raise MaxIterationsError(self._max_iterations, turn.iterations)

        return content

    async def _classify_and_maybe_correct(
        self,
        ctx: TurnContext,
        turn: Turn,
        assistant_msg: Message,
        *,
        history_includes_current: bool = False,
    ) -> bool:
        """Classify the turn and, if degenerate, inject a tailored correction.

        Returns ``True`` when a correction was injected and the caller should
        continue to the next iteration. Raises ``PolicyFailureError`` when a
        repeated-action loop persists after the maximum number of corrections.
        For empty responses, the caller's normal retry/fail logic is allowed to
        run after the correction budget is exhausted.
        """
        history = (
            ctx.running_history
            if history_includes_current
            else list(ctx.running_history) + [assistant_msg]
        )
        write_file_handler: Any | None = None
        append_to_file_handler: Any | None = None
        try:
            write_file_meta = self._tools.describe("write_file")
            write_file_handler = write_file_meta.handler
            append_to_file_meta = self._tools.describe("append_to_file")
            append_to_file_handler = append_to_file_meta.handler
        except Exception:  # noqa: BLE001
            pass

        correction = await classify_turn(
            turn,
            assistant_msg,
            history,
            ctx.allowed_tools or [],
            write_file_handler=write_file_handler,
            append_to_file_handler=append_to_file_handler,
        )
        if correction is None:
            return False

        regression_collector.maybe_collect_degenerate_turn(
            correction.pattern.value,
            history,
        )

        # De-duplicate repeated-identical-call corrections for the same tool.
        # The circuit breaker in _execute_tool_calls already blocks the call
        # and drops the schema; re-injecting the same correction for every
        # subsequent hallucinated call burns the correction budget and forces
        # an avoidable failure. One nudge per tool per turn is enough.
        if correction.pattern == DegeneratePattern.REPEATED_IDENTICAL_CALL:
            corrected_tools: set[str] = getattr(
                ctx, "_repeated_tools_corrected", set()
            )
            repeated_tools = set()
            for tc in assistant_msg.tool_calls or []:
                repeated_tools.add(tc.name)
            if repeated_tools and repeated_tools <= corrected_tools:
                return False
            corrected_tools.update(repeated_tools)
            ctx._repeated_tools_corrected = corrected_tools

        if ctx.correction_count < 3:
            await self._inject_correction(ctx, turn, correction)
            ctx.correction_count += 1
            return True
        if correction.pattern == DegeneratePattern.EMPTY_RESPONSE:
            # Empty responses are transient; let the policy engine decide whether
            # to retry or fail rather than forcing an immediate hard failure.
            return False
        raise PolicyFailureError(
            f"Degenerate pattern persisted after {ctx.correction_count} corrections: "
            f"{correction.pattern.value}. {correction.message}"
        )

    async def _inject_correction(
        self,
        ctx: TurnContext,
        turn: Turn,
        correction: Correction,
    ) -> None:
        """Append a correction message to the session and rebuild context."""
        msg = Message(
            role="user",
            content=correction.message,
            created_at=utcnow(),
            correction=True,
        )
        await self._store.append_message(ctx.session.id, msg)
        ctx.running_history.append(msg)
        self._builder.set_style_prefix(ctx.style_prefix)
        ctx.build_result = await self._builder.build(
            session=ctx.session,
            history=ctx.running_history,
            system_prompt=ctx.system_prompt,
            tools=ctx.tools,
            new_user_message=None,
        )

    async def _handle_tool_calls(
        self,
        ctx: TurnContext,
        turn: Turn,
        chat_response: ChatResponse,
        transition: TransitionCallback,
        set_typing: TypingCallback,
        assistant_msg: Message,
    ) -> TurnState:
        """Dispatch tool calls, handle delegation, rebuild context, and advance the turn."""
        await transition(turn, TurnState.EXECUTING_TOOLS, "")

        # Defensive: malformed tool arguments crash attribute-based lookups below.
        chat_response.tool_calls = [
            ToolCall(
                id=tc.id,
                name=tc.name,
                arguments=_normalize_tool_arguments(tc.arguments),
            )
            for tc in chat_response.tool_calls
        ]

        tool_names: list[str] = []
        for tc in chat_response.tool_calls:
            if tc.name == "describe_tool":
                raw_names = tc.arguments.get("names") if tc.arguments else []
                if isinstance(raw_names, str):
                    tool_names.append(f"describe_tool:{raw_names}")
                elif isinstance(raw_names, list):
                    for n in raw_names:
                        tool_names.append(f"describe_tool:{n}")
                else:
                    tool_names.append("describe_tool")
            else:
                tool_names.append(tc.name)
        ctx.tool_chain.extend(tool_names)
        logger.debug("Executing tools: %s", ", ".join(tool_names))
        await set_typing(True)

        # Show reasoning before tool status so user can see model's thinking
        if chat_response.reasoning_content:
            try:
                reasoning_display = f"💭 {chat_response.reasoning_content[:2000]}"
                if len(chat_response.reasoning_content) > 2000:
                    reasoning_display += "\n\n... (reasoning truncated)"
                await ctx.respond_callback(reasoning_display)
            except Exception:
                pass

        # Status update: tell user what we're doing (first iteration only)
        if turn.iterations == 0:
            status = self._format_tool_status(tool_names)
            if status:
                with contextlib.suppress(Exception):
                    await ctx.respond_callback(status)  # best-effort; don't fail the turn

        task_desc = (ctx.user_message.content or "").strip()
        use_policy_delegation = (
            "delegate_task" in self._tools.list_names()
            and self._policy.should_delegate(
                ctx.session,
                task_desc,
                turn.tool_calls_made,
                len(chat_response.tool_calls),
            )
        )
        ctx.delegated = use_policy_delegation

        if use_policy_delegation:
            await transition(turn, TurnState.AWAITING_SUBAGENT, "")
            tool_results, handles = await self._execute_policy_delegation(
                ctx.user_message, chat_response.tool_calls
            )
            ctx.artifact_handles.extend(handles)
            await transition(turn, TurnState.EXECUTING_TOOLS, "")
        else:
            tool_results, handles = await self._execute_tool_calls(
                ctx.session, chat_response.tool_calls, ctx.allowed_tools, ctx
            )
            ctx.artifact_handles.extend(handles)

        for result_msg in tool_results:
            await self._store.append_message(ctx.session.id, result_msg)

        await transition(turn, TurnState.BUILDING_CONTEXT, "")

        ctx.running_history.append(assistant_msg)
        ctx.running_history.extend(tool_results)

        # If we had to hard-block repeated list_tools, describe_tool, or any
        # other repeated identical tool calls, temporarily remove those schemas
        # from the model's available tools for the next iteration so it cannot
        # loop again. Removing the schema is the strongest signal for small models.
        if ctx.tools:
            blocked_names: set[str] = set()
            if getattr(ctx, "_list_tools_blocked", False):
                blocked_names.add("list_tools")
                ctx._list_tools_blocked = False
            if getattr(ctx, "_describe_tool_blocked", False):
                blocked_names.add("describe_tool")
                ctx._describe_tool_blocked = False
            repeated_blocked = getattr(ctx, "_repeated_tools_blocked", None) or set()
            if repeated_blocked:
                blocked_names.update(repeated_blocked)
                ctx._repeated_tools_blocked = set()
            if blocked_names:
                ctx.tools = [
                    schema for schema in ctx.tools
                    if schema.function.name not in blocked_names
                ]

        self._builder.set_style_prefix(ctx.style_prefix)
        ctx.build_result = await self._builder.build(
            session=ctx.session,
            history=ctx.running_history,
            system_prompt=ctx.system_prompt,
            tools=ctx.tools,
            new_user_message=None,
        )

        turn.tool_calls_made += len(chat_response.tool_calls)
        turn.iterations += 1
        return TurnState.BUILDING_CONTEXT

    async def _run_inference_streaming(
        self, ctx: TurnContext, turn: Turn
    ) -> ChatResponse:
        """Stream inference and accumulate a ChatResponse equivalent."""
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_call_buffers: dict[int, dict[str, Any]] = {}
        finish_reason = "unknown"
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        assert ctx.build_result is not None
        assert ctx.stream_callback is not None

        stream = self._inference.chat_stream(
            messages=ctx.build_result.messages,
            tools=ctx.tools,
            slot_id=ctx.slot_id,
            reasoning_budget=turn.reasoning_budget,
            max_tokens=self._max_tokens,
        )

        any_chunk_received = False
        while True:
            # Use a longer timeout for the very first chunk because the model
            # server may still be processing a long prompt without emitting
            # tokens.  After tokens start flowing, switch to the tight timeout.
            timeout = (
                _STREAM_INACTIVITY_TIMEOUT
                if any_chunk_received
                else _STREAM_FIRST_CHUNK_TIMEOUT
            )
            try:
                delta = await asyncio.wait_for(stream.__anext__(), timeout=timeout)
            except StopAsyncIteration:
                break
            except TimeoutError:
                if any_chunk_received:
                    logger.warning(
                        "Streaming inference inactive for %.1fs; finishing with %d content "
                        "chars and %d tool-call buffers accumulated so far",
                        _STREAM_INACTIVITY_TIMEOUT,
                        sum(len(p) for p in content_parts),
                        len(tool_call_buffers),
                    )
                else:
                    logger.warning(
                        "Streaming inference produced no chunks within %.1fs "
                        "(likely long prompt processing); finishing empty",
                        _STREAM_FIRST_CHUNK_TIMEOUT,
                    )
                if finish_reason == "unknown":
                    finish_reason = "stop"
                break

            any_chunk_received = True

            if delta.reasoning_content and not turn.thinking_aborted:
                thinking_chars = sum(len(p) for p in reasoning_parts) + len(delta.reasoning_content)
                # Rough token estimate: 4 characters per token
                if thinking_chars > turn.reasoning_budget * 4:
                    logger.warning(
                        "Thinking budget exceeded (%d chars ≈ %d tokens > %d budget)",
                        thinking_chars,
                        thinking_chars // 4,
                        turn.reasoning_budget,
                    )
                    raise ThinkingBudgetExceededError(
                        f"Thinking budget exceeded ({thinking_chars // 4} tokens > "
                        f"{turn.reasoning_budget})"
                    )

            if delta.content:
                content_parts.append(delta.content)
                await ctx.stream_callback(delta.content)

            if delta.reasoning_content:
                reasoning_parts.append(delta.reasoning_content)

            if delta.tool_call_chunks:
                for tc in delta.tool_call_chunks:
                    idx = tc.get("index", 0)
                    if idx not in tool_call_buffers:
                        tool_call_buffers[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc.get("id"):
                        tool_call_buffers[idx]["id"] = tc["id"]
                    fn = tc.get("function", {}) or {}
                    if fn.get("name"):
                        tool_call_buffers[idx]["name"] = fn["name"]
                    if fn.get("arguments"):
                        tool_call_buffers[idx]["arguments"] += fn["arguments"]

            if delta.finish_reason is not None:
                finish_reason = delta.finish_reason

            if delta.prompt_tokens or delta.completion_tokens or delta.total_tokens:
                prompt_tokens = delta.prompt_tokens
                completion_tokens = delta.completion_tokens
                total_tokens = delta.total_tokens

        content = "".join(content_parts)
        reasoning_content = "".join(reasoning_parts) if reasoning_parts else None

        tool_calls: list[ToolCall] = []
        for idx in sorted(tool_call_buffers.keys()):
            buf = tool_call_buffers[idx]
            if not buf["name"]:
                continue
            try:
                arguments = json.loads(buf["arguments"]) if buf["arguments"] else {}
            except json.JSONDecodeError as exc:
                repaired = repair_json(buf["arguments"]) if buf["arguments"] else None
                if repaired is not None:
                    logger.info(
                        "Repaired malformed tool_call arguments for %r in streaming path",
                        buf["name"],
                    )
                    arguments = json.loads(repaired)
                else:
                    logger.warning(
                        "tool_call arguments for %r are malformed JSON (%s); treating as empty",
                        buf["name"],
                        exc,
                    )
                    arguments = {}
            if not isinstance(arguments, dict):
                logger.warning(
                    "tool_call arguments for %r are not a dict: %s",
                    buf["name"],
                    type(arguments).__name__,
                )
                continue
            tool_calls.append(
                ToolCall(
                    id=buf["id"] or f"call_{idx}",
                    name=buf["name"],
                    arguments=arguments,
                )
            )

        # Fallback: Qwen3.5 in reasoning mode sometimes emits tool calls inside
        # <think> blocks (which land in reasoning_content) but omits the structured
        # tool_call_chunks. Parse XML-style <tool_call> tags as a safety net.
        if not tool_calls:
            combined = ""
            if reasoning_content:
                combined += reasoning_content + "\n"
            if content:
                combined += content + "\n"
            if combined:
                fallback = _extract_tool_calls_from_text(combined)
                if fallback:
                    tool_calls = fallback
                    logger.info(
                        "Recovered %d tool call(s) from reasoning/content XML fallback",
                        len(tool_calls),
                    )

        if finish_reason == "unknown" and tool_calls:
            finish_reason = "tool_calls"

        return ChatResponse(
            content=content,
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    async def _execute_tool_calls(
        self,
        session: Session,
        tool_calls: list[ToolCall],
        allowed_tools: list[str] | None = None,
        ctx: "TurnContext | None" = None,
    ) -> tuple[list[Message], list[str]]:
        """Execute tool calls and return result messages and artifact handles.

        Tools marked ``ordering="serial"`` or requiring confirmation run
        sequentially; everything else is dispatched concurrently via
        :func:`asyncio.gather` to avoid stacking latencies.
        """
        result_messages: list[Message] = []
        artifact_handles: list[str] = []

        # Defensive: ensure every tool-call argument payload is a dict.  Non-dict
        # arguments (strings, lists, None) come from malformed model output or
        # legacy DB rows and would otherwise crash attribute-based lookups.
        normalized_tool_calls: list[ToolCall] = []
        for tc in tool_calls:
            norm_args = _normalize_tool_arguments(tc.arguments)
            if norm_args is not tc.arguments:
                regression_collector.maybe_collect_malformed_tool_call(
                    tc.name,
                    tc.arguments,
                    source="_execute_tool_calls normalization",
                )
                tc = ToolCall(id=tc.id, name=tc.name, arguments=norm_args)
            normalized_tool_calls.append(tc)
        tool_calls = normalized_tool_calls

        original_tool_calls = list(tool_calls)

        # Circuit breaker: repeated list_tools calls are a common degenerate loop.
        # Once list_tools has been called in this turn (or in any prior turn of
        # the same session), re-executing it wastes context and tokens. We keep
        # one real execution so the model sees the tool list, but every repeat
        # is replaced with a synthetic result that includes the complete list
        # and a forceful instruction to stop.
        # Note: ctx.tool_chain has already been extended with the current batch
        # by _handle_tool_calls, so we look at the slice before this batch.
        current_batch_size = len(original_tool_calls)
        prior_tool_chain = (
            ctx.tool_chain[:-current_batch_size]
            if ctx is not None and current_batch_size > 0
            else []
        )
        prior_list_tools_count = prior_tool_chain.count("list_tools")
        seen_list_tools = prior_list_tools_count > 0
        list_tools_block_results: dict[str, Message] = {}
        blocked_any_list_tools = False
        if seen_list_tools or any(tc.name == "list_tools" for tc in original_tool_calls):
            list_tools_deduped: list[ToolCall] = []
            for tc in original_tool_calls:
                if tc.name == "list_tools":
                    if seen_list_tools:
                        # Any list_tools after the first one in the session is a
                        # degenerate loop. Hard-block it and mark that we need to
                        # drop the list_tools schema from the next prompt.
                        blocked_any_list_tools = True
                        list_tools_block_results[tc.id] = Message(
                            role="tool",
                            content=(
                                "🛑 STOP. You have already called list_tools. "
                                "The complete tool list is in the system prompt "
                                "and in the previous list_tools result. "
                                "list_tools is now DISABLED for the rest of this "
                                "turn. Do not call it again. Choose a "
                                "specific tool from the list and call it, or reply "
                                "directly to the user."
                            ),
                            tool_call_id=tc.id,
                            created_at=utcnow(),
                        )
                    else:
                        # First list_tools in this batch: allow it, but mark seen
                        # so any additional list_tools calls are blocked.
                        seen_list_tools = True
                        prior_list_tools_count += 1
                        list_tools_deduped.append(tc)
                else:
                    list_tools_deduped.append(tc)
            tool_calls = list_tools_deduped

        # Circuit breaker: repeated describe_tool calls with the same name are a
        # common degenerate pattern. After the 3rd unique describe_tool name, we
        # keep executing it but mark that the describe_tool schema should be
        # dropped from the next prompt so the model cannot binge on it.
        #
        # Build the set of already-described names from previous assistant
        # messages. We cannot slice ctx.tool_chain because describe_tool entries
        # are expanded to one entry per name, so the batch size in tool_chain
        # does not match len(original_tool_calls).
        prior_describe_tool_names: set[str] = set()
        if ctx is not None:
            for msg in ctx.running_history:
                if msg.role == "assistant" and msg.tool_calls:
                    for prev_tc in msg.tool_calls:
                        if prev_tc.name != "describe_tool":
                            continue
                        raw = prev_tc.arguments.get("names") if prev_tc.arguments else []
                        if isinstance(raw, str):
                            prior_describe_tool_names.add(raw)
                        elif isinstance(raw, list):
                            prior_describe_tool_names.update(raw)
        describe_tool_block_results: dict[str, Message] = {}
        blocked_describe_tool_binge = False
        if any(tc.name == "describe_tool" for tc in original_tool_calls):
            describe_tool_deduped: list[ToolCall] = []
            for tc in original_tool_calls:
                if tc.name == "describe_tool":
                    raw_names = tc.arguments.get("names") if tc.arguments else []
                    if isinstance(raw_names, str):
                        names = {raw_names}
                    elif isinstance(raw_names, list):
                        names = set(raw_names)
                    else:
                        names = set()
                    # Block if we've already described 3+ unique tools in this
                    # session, or if this call repeats any name we've seen
                    # (including within the current batch).
                    already_seen = bool(names & prior_describe_tool_names)
                    if len(prior_describe_tool_names) >= 3 or already_seen:
                        blocked_describe_tool_binge = True
                        describe_tool_block_results[tc.id] = Message(
                            role="tool",
                            content=(
                                "🛑 STOP. You have already called describe_tool enough. "
                                "The tool schemas are in the previous describe_tool results. "
                                "describe_tool is now DISABLED for the rest of this "
                                "turn. Stop inspecting tools and call one, or "
                                "reply directly to the user."
                            ),
                            tool_call_id=tc.id,
                            created_at=utcnow(),
                        )
                    else:
                        prior_describe_tool_names.update(names)
                        describe_tool_deduped.append(tc)
                else:
                    describe_tool_deduped.append(tc)
            tool_calls = describe_tool_deduped

        # Circuit breaker: repeated identical calls within the current turn.
        # If the model emits the exact same tool call as any previous assistant
        # message in this turn, block it and drop that schema from the next
        # prompt. This prevents loops like search_memory(query=...) or
        # read_file(path=...) from burning tokens. We also dedupe within the
        # current batch so a model cannot emit the same call twice at once.
        #
        # Exception: if the previous identical call produced a transient failure
        # (TIMEOUT or TRANSIENT_OTHER), allow a capped number of retries.
        repeated_block_results: dict[str, Message] = {}
        blocked_repeated_tools: set[str] = set()
        if ctx is not None:
            previous_keys: set[_ToolCallKey] = set()
            result_categories = _latest_tool_result_categories(ctx.running_history)
            previous_key_categories: dict[_ToolCallKey, ToolResultCategory] = {}
            for msg in ctx.running_history:
                if msg.role == "assistant" and msg.tool_calls:
                    for tc in msg.tool_calls:
                        key = _tool_call_key(tc)
                        previous_keys.add(key)
                        category = result_categories.get(tc.id)
                        if category is not None:
                            previous_key_categories[key] = category

            retry_counts = ctx._tool_call_retry_counts

            deduped: list[ToolCall] = []
            current_keys: set[_ToolCallKey] = set()
            for tc in tool_calls:
                key = _tool_call_key(tc)
                if key in current_keys:
                    blocked_repeated_tools.add(tc.name)
                    repeated_block_results[tc.id] = Message(
                        role="tool",
                        content=(
                            f"🛑 STOP. You already called {tc.name} with these "
                            "exact arguments in this turn; repeating it will "
                            "return the same result. This tool is now DISABLED "
                            "for the rest of this turn. Use a different "
                            "tool or reply directly to the user."
                        ),
                        tool_call_id=tc.id,
                        created_at=utcnow(),
                    )
                    continue

                if key in previous_keys:
                    category = previous_key_categories.get(
                        key, ToolResultCategory.SUCCESS
                    )
                    if category in (
                        ToolResultCategory.TIMEOUT,
                        ToolResultCategory.TRANSIENT_OTHER,
                    ):
                        count = retry_counts.get(key, 0)
                        if count >= self._max_retries_for_failed_tool_call:
                            blocked_repeated_tools.add(tc.name)
                            url = _extract_url_from_tool_call(tc)
                            repeated_block_results[tc.id] = Message(
                                role="tool",
                                content=_format_retry_exhausted_message(
                                    tc.name, category, count, url
                                ),
                                tool_call_id=tc.id,
                                created_at=utcnow(),
                            )
                            continue

                        if category == ToolResultCategory.TIMEOUT:
                            url = _extract_url_from_tool_call(tc)
                            proposed_timeout = _escalated_timeout_seconds(
                                tc, count
                            )
                            if not _consume_url_budget(
                                ctx, url, proposed_timeout
                            ):
                                blocked_repeated_tools.add(tc.name)
                                repeated_block_results[tc.id] = Message(
                                    role="tool",
                                    content=_format_retry_exhausted_message(
                                        tc.name,
                                        category,
                                        count,
                                        url,
                                        budget_exhausted=True,
                                    ),
                                    tool_call_id=tc.id,
                                    created_at=utcnow(),
                                )
                                continue
                            tc = _tool_call_with_timeout(tc, proposed_timeout)

                        retry_counts[key] = count + 1
                        current_keys.add(key)
                        deduped.append(tc)
                    else:
                        # SUCCESS, BLOCKED, NOT_FOUND, or missing category:
                        # fail-fast / do not retry.
                        blocked_repeated_tools.add(tc.name)
                        repeated_block_results[tc.id] = Message(
                            role="tool",
                            content=(
                                f"🛑 STOP. You already called {tc.name} with these "
                                "exact arguments in this turn; repeating it will "
                                "return the same result. This tool is now DISABLED "
                                "for the rest of this turn. Use a different "
                                "tool or reply directly to the user."
                            ),
                            tool_call_id=tc.id,
                            created_at=utcnow(),
                        )
                    continue

                current_keys.add(key)
                deduped.append(tc)
            tool_calls = deduped

        # Persist the block signals on the context so _handle_tool_calls can drop
        # the corresponding schemas from the next prompt.
        if ctx is not None:
            if blocked_any_list_tools:
                ctx._list_tools_blocked = True
            if blocked_describe_tool_binge:
                ctx._describe_tool_blocked = True
            if blocked_repeated_tools:
                ctx._repeated_tools_blocked = blocked_repeated_tools

        if len(tool_calls) > self._max_tool_calls_per_turn:
            logger.warning(
                "Model requested %d tool calls; capping at %d",
                len(tool_calls),
                self._max_tool_calls_per_turn,
            )
            # Return error results for the excess calls
            for tc in tool_calls[self._max_tool_calls_per_turn :]:
                msg = Message(
                    role="tool",
                    content=(
                        f"Tool call {tc.name} was rejected: too many tool calls "
                        f"in this turn (limit: {self._max_tool_calls_per_turn})."
                    ),
                    tool_call_id=tc.id,
                    created_at=utcnow(),
                )
                result_messages.append(msg)
            tool_calls = tool_calls[: self._max_tool_calls_per_turn]

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
                try:
                    result = await self._dispatch_tool_call(session, tc, allowed_tools)
                except Exception as exc:  # noqa: BLE001 — concurrent tool shield
                    logger.exception("Tool call %s failed during concurrent dispatch", tc.name)
                    result = ToolCallResult.error(
                        f"Tool {tc.name} failed: {exc}", error_type=type(exc).__name__
                    )
                    if self._event_bus is not None:
                        await self._event_bus.publish(
                            "tool_error",
                            {
                                "tool_name": tc.name,
                                "error": str(exc),
                                "error_type": type(exc).__name__,
                                "platform": "orchestrator",
                            },
                        )
                return idx, result

            for idx, result in await asyncio.gather(
                *[_run_one(i) for i in concurrent_indices]
            ):
                concurrent_results[idx] = result

        # Run serial tools sequentially. We intentionally do NOT wrap each
        # call in try/except because serial tools may include confirmation-
        # gated tools where a failure should stop the turn.
        serial_results: dict[int, ToolCallResult] = {}
        for idx in serial_indices:
            tc = tool_calls[idx]
            result = await self._dispatch_tool_call(session, tc, allowed_tools)
            serial_results[idx] = result

        # Reassemble in original emission order for trace consistency
        dispatched_ids = {tc.id for tc in tool_calls}
        dispatched_idx = 0
        for tc in original_tool_calls:
            if tc.id in list_tools_block_results:
                result_messages.append(list_tools_block_results[tc.id])
                continue
            if tc.id in describe_tool_block_results:
                result_messages.append(describe_tool_block_results[tc.id])
                continue
            if tc.id in repeated_block_results:
                result_messages.append(repeated_block_results[tc.id])
                continue
            if tc.id not in dispatched_ids:
                # Tool was removed by the per-turn cap; its rejection message is
                # already in result_messages.
                continue

            result = (
                concurrent_results[dispatched_idx]
                if dispatched_idx in concurrent_results
                else serial_results[dispatched_idx]
            )
            result = self._scan_tool_result(result)

            # Capture transient failures as regression fixtures if enabled.
            if (
                isinstance(result.content, str)
                and _is_retryable_tool_result(result.content)
            ):
                regression_collector.maybe_collect_tool_failure(
                    tc.name,
                    tc.arguments or {},
                    result.content,
                )

            # Circuit breaker: detect repeated empty-arg failures
            is_empty_args = tc.arguments is None or tc.arguments == {}
            looks_like_missing_arg_error = (
                result.status == "error"
                and isinstance(result.content, str)
                and (
                    "requires a" in result.content.lower()
                    or "missing" in result.content.lower()
                    or "requires" in result.content.lower()
                )
            )
            if is_empty_args and looks_like_missing_arg_error and ctx is not None:
                count = ctx.empty_tool_failure_counts.get(tc.name, 0) + 1
                ctx.empty_tool_failure_counts[tc.name] = count
                if count >= 3:
                    result = ToolCallResult.error(
                        f"🛑 CIRCUIT BREAKER: You have called {tc.name} with "
                        f"missing/empty arguments {count} times. You are stuck in a "
                        "loop and cannot generate the correct JSON payload. "
                        "STOP calling this tool. Instead, write your response as "
                        "plain text for the user."
                    )

            # Truncate oversized tool results before re-prompting
            max_chars = self._policy.tool_result_max_chars(tc.name)
            if (
                isinstance(max_chars, int)
                and isinstance(result.content, str)
                and len(result.content) > max_chars
            ):
                result.content = result.content[:max_chars] + "\n... [truncated]"
                result.truncated = True

            if result.artifact_handle:
                artifact_handles.append(result.artifact_handle)

            msg = Message(
                role="tool",
                content=result.content,
                tool_call_id=tc.id,
                created_at=utcnow(),
            )
            result_messages.append(msg)
            dispatched_idx += 1

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

        # Truncate oversized delegation results before re-prompting
        max_chars = self._policy.tool_result_max_chars("delegate_task")
        if isinstance(max_chars, int) and isinstance(body, str) and len(body) > max_chars:
            body = body[:max_chars] + "\n... [truncated]"
            result.truncated = True

        artifact_handles: list[str] = []
        if result.artifact_handle:
            artifact_handles.append(result.artifact_handle)

        messages: list[Message] = []
        for i, tc in enumerate(tool_calls):
            content = (
                body
                if i == 0
                else f"(Same policy delegation as tool_call_id={tool_calls[0].id}.)\n{body}"
            )
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

        if self._policy.auto_approve(tool_name, session, self._tools):
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

    async def _meta_list_tools(
        self, _session: Session, tc: ToolCall, allowed_tools: list[str] | None
    ) -> ToolCallResult:
        tag = tc.arguments.get("tag") if tc.arguments else None
        content = await self._tools.meta_list_tools(tag, allowed_names=allowed_tools)
        return ToolCallResult(
            status="ok",
            content=content,
            artifact_handle=None,
            truncated=False,
        )

    async def _meta_describe_tool(
        self, _session: Session, tc: ToolCall, allowed_tools: list[str] | None
    ) -> ToolCallResult:
        raw_names = tc.arguments.get("names") if tc.arguments else []
        names: str | list[str] = raw_names if isinstance(raw_names, (str, list)) else []
        content = await self._tools.meta_describe_tool(names, allowed_names=allowed_tools)
        return ToolCallResult(
            status="ok",
            content=content,
            artifact_handle=None,
            truncated=False,
        )

    async def _meta_call_tool(
        self, session: Session, tc: ToolCall, allowed_tools: list[str] | None
    ) -> ToolCallResult:
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
            and tc.name not in self._meta_tools
            and tc.name not in allowed_tools
        ):
            return ToolCallResult.error(
                f"Tool '{tc.name}' is not available in this session context.",
            )

        # Handle meta-tools via dispatch table
        handler = self._meta_tools.get(tc.name)
        if handler is not None:
            return await handler(session, tc, allowed_tools)

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
        return result

    def _format_tool_status(self, tool_names: list[str]) -> str | None:
        """Format a human-readable status line for the tools about to run."""
        if not tool_names:
            return None
        emoji_map = {
            "browser_get": "🌐",
            "browser_login": "🔐",
            "write_file": "📝",
            "append_to_file": "📝",
            "edit_file": "📝",
            "read_file": "📄",
            "list_dir": "📁",
            "terminal": "💻",
            "glob": "🔍",
            "grep": "🔍",
            "http_get": "🌐",
            "delegate_task": "👤",
            "list_tools": "🛠️",
            "describe_tool": "🛠️",
            "create_scheduled_task": "⏰",
            "save_memory": "🧠",
            "search_memory": "🧠",
            "list_memories": "🧠",
            "delete_memory": "🧠",
            "read_artifact": "📦",
            "current_time": "🕐",
            "web_search": "🔍",
            "email_search_and_read": "📧",
            "send_email": "📧",
            "accept_proposal": "✅",
            "reject_proposal": "❌",
            "show_proposal": "📋",
            "list_proposals": "📋",
        }
        parts = []
        for name in tool_names:
            emoji = emoji_map.get(name, "🛠️")
            parts.append(f"{emoji} {name}")
        return "Working: " + ", ".join(parts) + "..."

    def _scan_tool_result(self, result: ToolCallResult) -> ToolCallResult:
        """Run injection scanner over a tool result, annotating if triggered."""
        if self._injection_scanner is None or not result.content:
            return result
        scan = self._injection_scanner.scan(result.content)
        if scan.triggered:
            result.content = self._injection_scanner.wrap(result.content, scan.reasons)
        return result
