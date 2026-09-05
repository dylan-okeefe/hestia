"""Tool registry with meta-tool dispatch."""

import asyncio
import json
import logging
from types import ModuleType
from typing import Any

from hestia.artifacts.store import ArtifactStore
from hestia.core.types import FunctionSchema, ToolSchema
from hestia.errors import HestiaError, ToolExecutionError
from hestia.tools.metadata import ToolMetadata, tool
from hestia.tools.types import ToolCallResult


class ToolError(HestiaError):
    """Tool-related error."""

    pass


class ToolNotFoundError(ToolError):
    """Tool not found in registry."""

    pass


class ToolBlockedError(ToolError):
    """CapabilityGate denied the invocation (chokepoint enforcement)."""

    pass


class ToolConfirmationRequiredError(ToolError):
    """Gate escalated the invocation to an interactive confirmation.

    Carries the CapabilityResult (including ``request_token``) so the
    caller with a confirmation surface can resolve it and re-invoke with a
    ``pre_gated`` context.
    """

    def __init__(self, message: str, result: Any = None) -> None:
        super().__init__(message)
        self.result = result


class ToolRegistry:
    """Registry for tools with meta-tool dispatch.

    The meta-tool pattern reduces tool overhead from ~3000 tokens (listing all tool
    schemas) to ~80 tokens (just list_tools and call_tool schemas).
    """

    def __init__(self, artifact_store: ArtifactStore):
        """Initialize with an artifact store for large results."""
        # Insertion-ordered (Python 3.7+); tests rely on registration order for list_names().
        self._tools: dict[str, ToolMetadata] = {}
        self._artifact_store = artifact_store
        self._gate: Any = None

    def bind_gate(self, gate: Any) -> None:
        """Bind the CapabilityGate this registry enforces (L245 chokepoint).

        Once bound, every ``call`` with an ``enforce`` context is gated here —
        callers cannot bypass policy by invoking the handler directly.
        """
        self._gate = gate

    def register(self, func: Any) -> None:
        """Register a function decorated with @tool.

        Args:
            func: Function with __hestia_tool__ metadata attached

        Raises:
            ValueError: If func is not decorated with @tool
            ValueError: If tool name is already registered
        """
        meta = getattr(func, "__hestia_tool__", None)
        if meta is None:
            raise ValueError(f"{func} is not decorated with @tool")
        if meta.name in self._tools:
            raise ValueError(f"Tool {meta.name!r} already registered")
        self._tools[meta.name] = meta

    def register_module(self, module: ModuleType) -> None:
        """Scan a module and register all @tool-decorated functions."""
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if callable(attr) and hasattr(attr, "__hestia_tool__"):
                self.register(attr)

    def list_names(self, tag: str | None = None) -> list[str]:
        """List registered tool names.

        Args:
            tag: Optional tag filter

        Returns:
            Sorted list of tool names
        """
        if tag is None:
            return sorted(self._tools.keys())
        return sorted(n for n, m in self._tools.items() if tag in m.tags)

    def describe(self, name: str) -> ToolMetadata:
        """Get metadata for a tool.

        Args:
            name: Tool name

        Returns:
            ToolMetadata

        Raises:
            ToolNotFoundError: If tool doesn't exist
        """
        if name not in self._tools:
            raise ToolNotFoundError(f"Tool not found: {name}")
        return self._tools[name]

    async def call(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        context: Any,
    ) -> ToolCallResult:
        """Dispatch a tool call.

        Handles truncation and auto-promotion to artifacts for large results.

        Args:
            name: Tool name
            arguments: Tool arguments
            context: REQUIRED :class:`~hestia.tools.context.ToolCallContext`
                describing the caller (L245 strict mode). With a gate bound
                and ``mode="enforce"`` the registry evaluates the gate here;
                ``pre_gated`` carries an orchestrator-made decision bound to
                exactly this tool.

        Returns:
            ToolCallResult with status, content, and optional artifact handle

        Raises:
            ToolBlockedError: Policy denial - gate denied an enforce call,
                or the pre_gated decision itself is a denial.
            ToolConfirmationRequiredError: Gate escalated to confirmation.
            ValueError: Programming error - a pre_gated decision replayed
                for a tool it was not made for.
            RuntimeError: No capability gate is bound (every mode requires
                one; there is no passthrough).
            TypeError: Context missing or wrong type.
        """
        meta = self.describe(name)
        if meta.handler is None:
            raise ToolError(f"Tool {name!r} has no handler")

        from hestia.tools.context import ToolCallContext  # local: avoids gate<->registry cycle

        if not isinstance(context, ToolCallContext):
            raise TypeError(
                f"ToolRegistry.call requires a ToolCallContext (got {type(context).__name__})"
            )

        # L245 INVARIANT: every mode requires a bound gate. There is no
        # passthrough configuration - a registry without a gate refuses all
        # calls. Wiring that wants "no policy" must bind an explicit
        # permissive fake so the choice is visible in the wiring itself.
        if self._gate is None:
            raise RuntimeError(
                f"ToolRegistry.call('{name}') in {context.mode} mode but no "
                "capability gate is bound - call bind_gate() at wiring time"
            )

        if context.mode == "enforce":
            from hestia.policy.gate import CapabilityRequest
            from hestia.policy.identity import Identity

            request = CapabilityRequest(
                actor=Identity(
                    platform=context.actor_platform,
                    platform_user=context.actor_platform_user,
                ),
                channel=context.channel,
                tool_name=name,
                inputs=dict(arguments),
                session_id=context.session_id,
                source_workflow_id=context.source_workflow_id,
            )
            result = await self._gate.check(
                request,
                injection_flagged=context.injection_flagged,
                allow_list=set(context.allow_list),
            )
            if not result.allowed:
                raise ToolBlockedError(
                    f"[CATEGORY: BLOCKED] Capability gate denied '{name}': "
                    f"{result.reason}"
                )
            if result.requires_confirmation:
                raise ToolConfirmationRequiredError(
                    f"Tool '{name}' requires operator confirmation",
                    result=result,
                )
        elif context.mode == "pre_gated":
            # Round-2 P3: two distinct failure shapes. A decision replayed
            # for the wrong tool is a programming error (ValueError); a
            # decision that says DENY is a policy denial (ToolBlockedError)
            # so handlers catching that type keep recognizing it.
            if context.pre_gated_result is None:  # defensive; post_init guards
                raise ValueError(
                    f"pre_gated context for '{name}' carries no decision"
                )
            if context.pre_gated_tool != name:
                raise ValueError(
                    f"pre_gated decision was for "
                    f"'{context.pre_gated_tool}', not '{name}' - "
                    "refusing to replay it for a different tool"
                )
            if not context.pre_gated_result.allowed:
                raise ToolBlockedError(
                    f"[CATEGORY: BLOCKED] pre_gated decision denied '{name}': "
                    f"{context.pre_gated_result.reason}"
                )

        # The prior handler catch was restricted to (TypeError, ValueError, OSError),
        # so RuntimeError, httpx.HTTPError, application-level exceptions from third-party
        # tools, etc. escaped the registry and aborted the whole turn. We now catch broad
        # Exception (but NOT BaseException — CancelledError and KeyboardInterrupt must
        # still propagate) and wrap in ToolExecutionError so the orchestrator can dispatch
        # on type via ToolCallResult.error_type instead of string-matching.
        try:
            raw = await meta.handler(**arguments)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — documented exception contract
            wrapped = ToolExecutionError(name, e)
            return ToolCallResult.error(
                content=f"{wrapped.inner_type}: {e}",
                error_type=wrapped.inner_type,
            )

        content_str = json.dumps(raw, indent=2) if isinstance(raw, (dict, list)) else str(raw)

        return await self._postprocess(content_str, meta)

    async def _postprocess(self, content: str, meta: ToolMetadata) -> ToolCallResult:
        """Post-process tool result: truncate and/or promote to artifact.

        ``ArtifactStore.store`` is synchronous (writes bytes + JSON metadata
        to disk); we offload it via ``asyncio.to_thread`` so the event
        loop stays responsive during large-artifact writes.
        """
        size = len(content)

        if size > meta.max_inline_chars:
            # Large result: store full content as artifact, return a preview
            handle = await asyncio.to_thread(
                self._artifact_store.store,
                content.encode("utf-8"),
                content_type="text/plain",
                source_tool=meta.name,
            )
            preview = content[: meta.max_inline_chars]
            return ToolCallResult(
                status="ok",
                content=(
                    f"[full result stored as artifact {handle}; "
                    f"showing first {len(preview)} of {size} chars]\n\n{preview}"
                ),
                artifact_handle=handle,
                truncated=True,
            )

        return ToolCallResult(
            status="ok",
            content=content,
            artifact_handle=None,
            truncated=False,
        )

    # --- Meta-tool schemas (what the model actually sees) ---

    def meta_tool_schemas(self) -> list[ToolSchema]:
        """Return the three meta-tools (list_tools, describe_tool, call_tool) as ToolSchema."""
        list_tools_schema = ToolSchema(
            type="function",
            function=FunctionSchema(
                name="list_tools",
                description=(
                    "List all available tools. Returns tool names and one-line descriptions. "
                    "Only call this when the user asks about your capabilities or when you "
                    "genuinely do not know which tool to use. "
                    "For greetings, casual chat, or questions you can answer directly, reply "
                    "without calling any tool."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "tag": {
                            "type": "string",
                            "description": "Optional tag filter",
                        },
                    },
                },
            ),
        )

        describe_tool_schema = ToolSchema(
            type="function",
            function=FunctionSchema(
                name="describe_tool",
                description=(
                    "Get the full JSON parameter schema and description for one or more tools. "
                    "Only call this when you already intend to use a specific tool and need "
                    "to know its exact argument names, types, and defaults. "
                    "Do not call this for greetings, casual chat, or questions you can answer "
                    "directly."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Tool name(s) to describe. Can be a single name or a list.",
                        },
                    },
                    "required": ["names"],
                },
            ),
        )

        call_tool_schema = ToolSchema(
            type="function",
            function=FunctionSchema(
                name="call_tool",
                description=(
                    "Invoke a tool by name with arguments. You do not need to call list_tools "
                    "first if you already know the tool name. Use describe_tool only when you "
                    "need exact parameter names. Arguments must be a valid JSON object. "
                    "Example: call_tool({\"name\": \"write_file\", "
                    "\"arguments\": {\"path\": \"<path>\", \"content\": \"# Notes\\n\"}}). "
                    "For greetings, casual chat, or anything that does not require a tool, "
                    "reply directly instead of calling a tool. "
                    "Each write_file call can write up to 50000 characters; use append_to_file for additional chunks. "
                    "For large files, first create the file with a short header using write_file, "
                    "then add sections with append_to_file. "
                    "When a tool result says it is stored as an artifact, use read_artifact "
                    "with start_at/length to fetch the remaining content in chunks."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the tool to call",
                        },
                        "arguments": {
                            "type": "object",
                            "description": "Arguments for the tool as a JSON object",
                        },
                    },
                    "required": ["name", "arguments"],
                },
            ),
        )

        return [list_tools_schema, describe_tool_schema, call_tool_schema]

    def direct_schema(self, name: str, *, description: str | None = None) -> ToolSchema | None:
        """Return a named tool's schema for first-class (direct) exposure.

        Most tools stay hidden behind the meta-tools (list_tools/describe_tool/
        call_tool) to keep per-turn token cost down. A tool that must be
        callable during casual chat — where the system prompt forbids the
        meta-tools — needs its schema visible directly; this builds it from
        the tool's registered metadata. Returns None if the tool is not
        registered.
        """
        meta = self._tools.get(name)
        if meta is None:
            return None
        return ToolSchema(
            type="function",
            function=FunctionSchema(
                name=meta.name,
                description=description or meta.public_description,
                parameters=meta.parameters_schema,
            ),
        )

    async def meta_list_tools(
        self,
        tag: str | None = None,
        allowed_names: list[str] | None = None,
    ) -> str:
        """Handler for the list_tools meta-tool.

        Args:
            tag: Optional tag filter
            allowed_names: Optional list of allowed tool names (for session filtering)
        """
        names = self.list_names(tag=tag)
        if allowed_names is not None:
            names = [n for n in names if n in allowed_names]
        lines = []
        for n in names:
            m = self._tools[n]
            caps = ", ".join(m.capabilities) or "none"
            lines.append(f"- {n}: {m.public_description} [caps: {caps}]")
        return "\n".join(lines) if lines else "(no tools)"

    async def meta_describe_tool(
        self,
        names: str | list[str],
        allowed_names: list[str] | None = None,
    ) -> str:
        """Handler for the describe_tool meta-tool.

        Args:
            names: Tool name or list of names to describe
            allowed_names: Optional list of allowed tool names (for session filtering)
        """
        if isinstance(names, str):
            names = [names]

        lines = []
        for n in names:
            if allowed_names is not None and n not in allowed_names:
                lines.append(f"- {n}: (not available in this session)")
                continue
            try:
                m = self.describe(n)
            except ToolNotFoundError:
                lines.append(f"- {n}: (tool not found)")
                continue

            caps = ", ".join(m.capabilities) or "none"
            lines.append(f"- {n}: {m.public_description} [caps: {caps}]")
            if m.parameters_schema:
                schema_str = json.dumps(m.parameters_schema, indent=2)
                indented = "\n".join("    " + ln for ln in schema_str.splitlines())
                lines.append(f"  schema:\n{indented}")
            else:
                lines.append("  schema: (no explicit schema — infer from description)")
        return "\n".join(lines) if lines else "(no tools)"

    async def meta_call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        context: Any,
    ) -> ToolCallResult:
        """Handler for the call_tool meta-tool."""
        try:
            return await self.call(name, arguments, context=context)
        except ToolNotFoundError:
            return ToolCallResult.error(
                content=f"Tool not found: {name}. Use list_tools to see available tools.",
                error_type="ToolNotFoundError",
            )


# Re-export for convenience
logger = logging.getLogger(__name__)

__all__ = [
    "ToolRegistry",
    "ToolMetadata",
    "tool",
    "ToolError",
    "ToolNotFoundError",
    "ToolBlockedError",
    "ToolConfirmationRequiredError",
]
