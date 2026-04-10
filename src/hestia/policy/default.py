"""Default policy engine with conservative decisions."""

from typing import TYPE_CHECKING

from hestia.core.types import Session
from hestia.errors import InferenceServerError, InferenceTimeoutError
from hestia.policy.engine import (
    PolicyEngine,
    RetryAction,
    RetryDecision,
)
from hestia.runtime_context import scheduler_tick_active

if TYPE_CHECKING:
    from hestia.tools.registry import ToolRegistry


class DefaultPolicyEngine(PolicyEngine):
    """Default conservative policies.

    These are safe defaults. Users can subclass or replace the policy engine
    to customize behavior.
    """

    def __init__(self, ctx_window: int = 32768) -> None:
        """Initialize with context window size.

        Args:
            ctx_window: Total context window size in tokens. Default assumes
                       llama-server with 32K slots.
        """
        self.ctx_window = ctx_window

    def should_delegate(
        self,
        session: Session,
        task_description: str,
        tool_chain_length: int = 0,
        projected_tool_calls: int = 0,
    ) -> bool:
        """Decide whether to delegate to a subagent.

        Delegation is recommended when:
        - Tool chain is getting long (>5 calls so far)
        - Task appears complex (keywords like "research", "analyze", "investigate")
        - User explicitly requests delegation

        Args:
            session: Current session
            task_description: Description of the task
            tool_chain_length: Number of tool calls made so far in this turn
            projected_tool_calls: Estimated remaining tool calls needed

        Returns:
            True if delegation is recommended
        """
        # Never recurse: subagent runs use platform "subagent"
        if session.platform == "subagent":
            return False

        # Explicit user request for delegation
        delegation_keywords = ["delegate", "subagent", "spawn task", "background task"]
        task_lower = task_description.lower()
        if any(kw in task_lower for kw in delegation_keywords):
            return True

        # Long tool chain - offload to subagent to keep parent context clean
        if tool_chain_length > 5:
            return True

        # Complex research tasks that might involve many steps
        research_keywords = ["research", "investigate", "analyze deeply", "comprehensive"]
        if any(kw in task_lower for kw in research_keywords):
            return True

        # High projected tool usage
        if projected_tool_calls > 3:
            return True

        return False

    def should_compress(self, session: Session, tokens_used: int, tokens_budget: int) -> bool:
        """Compress when we're over 85% of budget."""
        return tokens_used > int(tokens_budget * 0.85)

    def should_evict_slot(self, slot_id: int, pressure: float) -> bool:
        """Never evict slots in Phase 1b.

        Phase 2 will add slot management logic.
        """
        return False

    def retry_after_error(self, error: Exception, attempt: int) -> RetryDecision:
        """Retry transient inference errors once, then fail.

        Transient errors:
        - InferenceTimeoutError: server didn't respond in time
        - InferenceServerError: server returned 5xx or connection error

        Non-transient errors fail immediately.
        """
        if attempt >= 2:
            return RetryDecision(
                action=RetryAction.FAIL,
                reason="max attempts exceeded",
            )

        if isinstance(error, (InferenceTimeoutError, InferenceServerError)):
            return RetryDecision(
                action=RetryAction.RETRY_WITH_BACKOFF,
                backoff_seconds=1.0,
                reason="transient inference error",
            )

        # Non-transient errors (tool errors, logic errors, etc.) fail immediately
        return RetryDecision(
            action=RetryAction.FAIL,
            reason=f"non-transient error: {type(error).__name__}",
        )

    def turn_token_budget(self, session: Session) -> int:
        """Reserve space for system + history + response.

        Reserve 2048 tokens for model response, use 85% of remaining for input.
        """
        return int(self.ctx_window * 0.85) - 2048

    def tool_result_max_chars(self, tool_name: str) -> int:
        """Default 8000 chars for tool results.

        Individual tools can override via registry metadata.
        """
        return 8000

    def filter_tools(
        self,
        session: Session,
        tool_names: list[str],
        registry: "ToolRegistry",
    ) -> list[str]:
        """Filter available tools based on session context.

        Subagents are denied shell_exec and write_local to prevent
        uncontrolled modifications. Scheduler is denied shell_exec
        for headless safety.

        Args:
            session: Current session
            tool_names: List of tool names to filter
            registry: Tool registry for looking up capabilities

        Returns:
            Filtered list of allowed tool names
        """
        from hestia.tools.capabilities import SHELL_EXEC, WRITE_LOCAL

        if session.platform == "subagent":
            # Subagents: block shell_exec and write_local
            blocked = {SHELL_EXEC, WRITE_LOCAL}
            return [
                name for name in tool_names
                if not (set(registry.describe(name).capabilities) & blocked)
            ]

        if session.platform == "scheduler" or scheduler_tick_active.get():
            # Scheduler: block shell_exec for headless safety
            blocked = {SHELL_EXEC}
            return [
                name for name in tool_names
                if not (set(registry.describe(name).capabilities) & blocked)
            ]

        # CLI and other platforms: allow all tools
        return tool_names
