"""Turn execution phase: model inference, tool dispatch, confirmation gating."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from hestia.core.clock import utcnow
from hestia.core.inference import InferenceClient
from hestia.core.types import ChatResponse, Message, Session, ToolCall
from hestia.errors import (
    EmptyResponseError,
    InferenceServerError,
    MaxIterationsError,
    PolicyFailureError,
)
from hestia.orchestrator.types import TransitionCallback, Turn, TurnContext, TurnState
from hestia.policy.engine import PolicyEngine, RetryAction
from hestia.security import InjectionScanner
from hestia.tools.metadata import ToolMetadata
from hestia.tools.registry import ToolNotFoundError, ToolRegistry
from hestia.tools.types import ToolCallResult

if TYPE_CHECKING:
    from hestia.context.builder import ContextBuilder
    from hestia.persistence.sessions import SessionStore

logger = logging.getLogger(__name__)

ConfirmCallback = Callable[[str, dict[str, Any]], Awaitable[bool]]
TypingCallback = Callable[[bool], Awaitable[None]]


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
        stream: bool = False,
    ):
        self._tools = tool_registry
        self._inference = inference_client
        self._policy = policy
        self._builder = context_builder
        self._store = session_store
        self._confirm_callback = confirm_callback
        self._injection_scanner = injection_scanner
        self._max_iterations = max_iterations
        self._max_tool_calls_per_turn = max_tool_calls_per_turn
        self._stream = stream

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

            if ctx.stream_callback is not None and self._stream:
                chat_response = await self._run_inference_streaming(ctx, turn)
            else:
                chat_response = await self._inference.chat(
                    messages=ctx.build_result.messages,
                    tools=ctx.tools,
                    slot_id=ctx.slot_id,
                    reasoning_budget=turn.reasoning_budget,
                )

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

            if chat_response.finish_reason == "tool_calls":
                await transition(turn, TurnState.EXECUTING_TOOLS, "")

                tool_names = [tc.name for tc in chat_response.tool_calls]
                ctx.tool_chain.extend(tool_names)
                logger.debug("Executing tools: %s", ", ".join(tool_names))
                await set_typing(True)

                task_desc = (ctx.user_message.content or "").strip()
                use_policy_delegation = (
                    "delegate_task" in self._tools.list_names()
                    and self._policy.should_delegate(
                        session,
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
                        session, chat_response.tool_calls, ctx.allowed_tools
                    )
                    ctx.artifact_handles.extend(handles)

                for result_msg in tool_results:
                    await self._store.append_message(session.id, result_msg)

                await transition(turn, TurnState.BUILDING_CONTEXT, "")

                ctx.running_history.append(assistant_msg)
                ctx.running_history.extend(tool_results)
                self._builder.set_style_prefix(ctx.style_prefix)
                ctx.build_result = await self._builder.build(
                    session=session,
                    history=ctx.running_history,
                    system_prompt=ctx.system_prompt,
                    tools=ctx.tools,
                    new_user_message=None,
                )

                turn.tool_calls_made += len(chat_response.tool_calls)
                turn.iterations += 1
                continue

            elif chat_response.finish_reason in ("stop", "length"):
                content = chat_response.content or ""
                if not content.strip() and not chat_response.tool_calls:
                    # Empty response — retry via policy instead of failing immediately
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

                await set_typing(False)

                await transition(turn, TurnState.DONE, "")
                turn.final_response = content
                await ctx.respond_callback(content)
                break

            else:
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

        async for delta in self._inference.chat_stream(
            messages=ctx.build_result.messages,
            tools=ctx.tools,
            slot_id=ctx.slot_id,
            reasoning_budget=turn.reasoning_budget,
        ):
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
                raise InferenceServerError(
                    f"tool_call arguments for {buf['name']!r} are malformed JSON: {exc}"
                ) from exc
            if not isinstance(arguments, dict):
                raise InferenceServerError(
                    f"tool_call arguments for {buf['name']!r} are not a dict: "
                    f"{type(arguments).__name__}"
                )
            tool_calls.append(
                ToolCall(
                    id=buf["id"] or f"call_{idx}",
                    name=buf["name"],
                    arguments=arguments,
                )
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
        self, session: Session, tool_calls: list[ToolCall], allowed_tools: list[str] | None = None
    ) -> tuple[list[Message], list[str]]:
        """Execute tool calls and return result messages and artifact handles.

        Tools marked ``ordering="serial"`` or requiring confirmation run
        sequentially; everything else is dispatched concurrently via
        :func:`asyncio.gather` to avoid stacking latencies.
        """
        result_messages: list[Message] = []
        artifact_handles: list[str] = []

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
        return self._scan_tool_result(result)

    def _scan_tool_result(self, result: ToolCallResult) -> ToolCallResult:
        """Run injection scanner over a tool result, annotating if triggered."""
        if self._injection_scanner is None or not result.content:
            return result
        scan = self._injection_scanner.scan(result.content)
        if scan.triggered:
            result.content = self._injection_scanner.wrap(result.content, scan.reasons)
        return result
