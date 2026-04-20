"""Default policy engine with conservative decisions."""

from typing import TYPE_CHECKING

from hestia.config import PolicyConfig, TrustConfig
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


DEFAULT_DELEGATION_KEYWORDS: tuple[str, ...] = (
    "delegate",
    "subagent",
    "spawn task",
    "background task",
)

DEFAULT_RESEARCH_KEYWORDS: tuple[str, ...] = (
    "research",
    "investigate",
    "analyze deeply",
    "comprehensive",
)

DEFAULT_RETRY_MAX_ATTEMPTS: int = 2


class DefaultPolicyEngine(PolicyEngine):
    """Default conservative policies.

    These are safe defaults. Users can subclass or replace the policy engine
    to customize behavior.
    """

    def __init__(
        self,
        ctx_window: int = 8192,
        default_reasoning_budget: int = 2048,
        trust: TrustConfig | None = None,
        config: PolicyConfig | None = None,
        trust_overrides: dict[str, TrustConfig] | None = None,
    ) -> None:
        """Initialize with context window size.

        Args:
            ctx_window: **Per-slot** context window in tokens. Must match
                your llama-server's `--ctx-size / --parallel`. Default
                (8K) matches `deploy/hestia-llama.service` out of the box.
            default_reasoning_budget: Default reasoning token budget.
            trust: Trust profile for auto-approval and capability gating.
                Defaults to paranoid (safest posture).
            config: Policy configuration for tunable behavior.
            trust_overrides: Per-user trust overrides keyed by
                ``platform:platform_user``.
        """
        self.ctx_window = ctx_window
        self._default_reasoning_budget = default_reasoning_budget
        self._trust = trust if trust is not None else TrustConfig()
        self._config = config if config is not None else PolicyConfig()
        self._trust_overrides = trust_overrides if trust_overrides is not None else {}

        self.retry_max_attempts = DEFAULT_RETRY_MAX_ATTEMPTS

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

        .. note::
            Keyword matching can produce surprising triggers. For example,
            "I'd like to research my family history" will match the
            "research" keyword and trigger delegation. Operators should
            override ``delegation_keywords`` via :class:`PolicyConfig` for
            production use.

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
        delegation = (
            DEFAULT_DELEGATION_KEYWORDS
            if self._config.delegation_keywords is None
            else self._config.delegation_keywords
        )
        task_lower = task_description.lower()
        if delegation and any(kw in task_lower for kw in delegation):
            return True

        # Long tool chain - offload to subagent to keep parent context clean
        if tool_chain_length > 5:
            return True

        # Complex research tasks that might involve many steps
        research = (
            DEFAULT_RESEARCH_KEYWORDS
            if self._config.research_keywords is None
            else self._config.research_keywords
        )
        if research and any(kw in task_lower for kw in research):
            return True

        # High projected tool usage
        return projected_tool_calls > 3

    def should_compress(self, session: Session, tokens_used: int, tokens_budget: int) -> bool:
        """Compress when we're over 85% of budget."""
        return tokens_used > int(tokens_budget * 0.85)

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

    def _trust_for(self, session: Session) -> TrustConfig:
        """Resolve trust config for a session, applying per-user overrides.

        Falls back to the default trust profile when no override exists
        or when session identity is missing.
        """
        key = f"{session.platform}:{session.platform_user}"
        if not session.platform or not session.platform_user:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                "Session %s has missing identity (platform=%r platform_user=%r); "
                "falling back to default trust",
                session.id,
                session.platform,
                session.platform_user,
            )
            return self._trust
        return self._trust_overrides.get(key, self._trust)

    def auto_approve(self, tool_name: str, session: Session) -> bool:
        """Return True if the trust profile auto-approves this tool."""
        trust = self._trust_for(session)
        approved = trust.auto_approve_tools
        if "*" in approved:
            return True
        return tool_name in approved

    def filter_tools(
        self,
        session: Session,
        tool_names: list[str],
        registry: "ToolRegistry",
    ) -> list[str]:
        """Filter available tools based on session context.

        Subagents are denied shell_exec and write_local to prevent
        uncontrolled modifications. Scheduler is denied shell_exec
        for headless safety. Both are denied email_send unless the
        trust profile explicitly allows it.

        Args:
            session: Current session
            tool_names: List of tool names to filter
            registry: Tool registry for looking up capabilities

        Returns:
            Filtered list of allowed tool names
        """
        from hestia.tools.capabilities import EMAIL_SEND, SHELL_EXEC, WRITE_LOCAL

        trust = self._trust_for(session)

        if session.platform == "subagent":
            blocked: set[str] = set()
            if not trust.subagent_shell_exec:
                blocked.add(SHELL_EXEC)
            if not trust.subagent_write_local:
                blocked.add(WRITE_LOCAL)
            if not trust.subagent_email_send:
                blocked.add(EMAIL_SEND)
            if not blocked:
                return tool_names
            return [
                name
                for name in tool_names
                if not (set(registry.describe(name).capabilities) & blocked)
            ]

        if session.platform == "scheduler" or scheduler_tick_active.get():
            blocked = set()
            if not trust.scheduler_shell_exec:
                blocked.add(SHELL_EXEC)
            if not trust.scheduler_email_send:
                blocked.add(EMAIL_SEND)
            if not blocked:
                return tool_names
            return [
                name
                for name in tool_names
                if not (set(registry.describe(name).capabilities) & blocked)
            ]

        # CLI and other platforms: allow all tools
        return tool_names

    def reasoning_budget(self, session: Session, iteration: int) -> int:
        """Use the configured default. Subagents get a smaller budget."""
        base = self._default_reasoning_budget
        if session is not None and session.platform == "subagent":
            return min(base, 1024)  # subagents don't need deep reasoning
        return base
