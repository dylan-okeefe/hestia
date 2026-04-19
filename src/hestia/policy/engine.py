"""PolicyEngine abstract interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from hestia.core.types import Session

if TYPE_CHECKING:
    from hestia.tools.registry import ToolRegistry


class RetryAction(Enum):
    """Actions the orchestrator can take after an error."""

    RETRY = "retry"
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    FAIL = "fail"


@dataclass
class RetryDecision:
    """Decision on how to handle a retryable error."""

    action: RetryAction
    backoff_seconds: float = 0.0
    reason: str = ""


class PolicyEngine(ABC):
    """Abstract policy engine.

    All "when/whether" decisions in the framework go through here.
    The orchestrator executes; the policy engine decides.
    """

    @abstractmethod
    def should_delegate(
        self,
        session: Session,
        task_description: str,
        tool_chain_length: int = 0,
        projected_tool_calls: int = 0,
    ) -> bool:
        """Should this task be delegated to a subagent?"""
        ...

    @abstractmethod
    def should_compress(self, session: Session, tokens_used: int, tokens_budget: int) -> bool:
        """Should we compress context before sending to model?"""
        ...

    @abstractmethod
    def should_evict_slot(self, slot_id: int, pressure: float) -> bool:
        """Should we evict this slot to free up resources?"""
        ...

    @abstractmethod
    def retry_after_error(self, error: Exception, attempt: int) -> RetryDecision:
        """How should we handle this error?"""
        ...

    @abstractmethod
    def turn_token_budget(self, session: Session) -> int:
        """How many tokens should we budget for this turn's input?"""
        ...

    @abstractmethod
    def tool_result_max_chars(self, tool_name: str) -> int:
        """Maximum characters to include for a tool result."""
        ...

    @abstractmethod
    def filter_tools(
        self,
        session: Session,
        tool_names: list[str],
        registry: "ToolRegistry",
    ) -> list[str]:
        """Filter available tools based on session context.

        Returns the subset of tool_names allowed for this session.
        """
        ...

    @abstractmethod
    def auto_approve(self, tool_name: str, session: Session) -> bool:
        """Whether a tool with requires_confirmation=True may run without
        a confirm_callback in the current session context.

        Returns True iff the trust profile has marked this tool as
        auto-approved for headless execution.
        """
        ...

    @abstractmethod
    def reasoning_budget(self, session: Session, iteration: int) -> int:
        """How many reasoning tokens to budget for this inference call."""
        ...
