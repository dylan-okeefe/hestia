# mypy: disable-error-code="no-untyped-def"
"""Shared helpers for integration tests."""

from hestia.core.types import ChatResponse


class FakeInferenceClient:
    """Fake inference client for testing."""

    def __init__(self, responses=None):
        """Initialize with optional list of responses."""
        self.model_name = "fake-model"
        self.responses = responses or []
        self.call_count = 0
        self.closed = False

    async def tokenize(self, text: str) -> list[int]:
        return [0] * (len(text) // 4 + 1)

    async def count_request(self, messages, tools):
        """Simple char-based token count."""
        total = 0
        for msg in messages:
            total += 10 + len(msg.content or "") // 4
        for _tool in tools or []:
            total += 50  # Tool schema cost
        return total

    async def chat(self, messages, tools=None, slot_id=None, **kwargs):
        """Return next canned response."""
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response

        # Default: simple text response
        self.call_count += 1
        return ChatResponse(
            content="Test response",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )

    async def close(self):
        """Mark as closed."""
        self.closed = True

    async def health(self):
        """Return fake health."""
        return {"status": "ok"}


class FakePolicyEngine:
    """Fake policy engine for testing."""

    def should_delegate(
        self,
        session,
        task_description,
        tool_chain_length: int = 0,
        projected_tool_calls: int = 0,
    ):
        return False

    def should_compress(self, session, tokens_used, tokens_budget):
        return False

    def retry_after_error(self, error, attempt):
        from hestia.policy.engine import RetryAction, RetryDecision

        return RetryDecision(action=RetryAction.FAIL)

    def filter_tools(self, session, tool_names, registry):
        return tool_names

    def turn_token_budget(self, session):
        return 4000

    def tool_result_max_chars(self, tool_name):
        return 4000

    def reasoning_budget(self, session, iteration):
        return 2048

    def auto_approve(self, tool_name, session):
        return False
