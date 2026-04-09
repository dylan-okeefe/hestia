"""Default policy engine with conservative decisions."""

from hestia.errors import InferenceServerError, InferenceTimeoutError
from hestia.policy.engine import (
    PolicyEngine,
    RetryAction,
    RetryDecision,
)
from hestia.core.types import Session


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

    def should_delegate(self, session: Session, task_description: str) -> bool:
        """Never delegate in Phase 1b.

        Phase 1c will add delegation logic.
        """
        return False

    def should_compress(
        self, session: Session, tokens_used: int, tokens_budget: int
    ) -> bool:
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
