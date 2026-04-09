"""Unit tests for PolicyEngine."""

import pytest

from hestia.core.types import Session, SessionState, SessionTemperature
from hestia.errors import InferenceServerError, InferenceTimeoutError
from hestia.policy.default import DefaultPolicyEngine
from hestia.policy.engine import RetryAction


@pytest.fixture
def policy():
    """Default policy engine fixture."""
    return DefaultPolicyEngine(ctx_window=32768)


@pytest.fixture
def sample_session():
    """Sample session fixture."""
    from datetime import datetime

    return Session(
        id="test_session",
        platform="test",
        platform_user="user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )


class TestShouldCompress:
    """Tests for should_compress policy."""

    def test_no_compression_below_threshold(self, policy, sample_session):
        """Don't compress when under 85% of budget."""
        assert not policy.should_compress(sample_session, 1000, 2000)
        assert not policy.should_compress(sample_session, 1699, 2000)

    def test_compression_at_threshold(self, policy, sample_session):
        """Compress when strictly over 85% of budget."""
        assert not policy.should_compress(sample_session, 1700, 2000)  # exactly 85%, no compress
        assert policy.should_compress(sample_session, 1701, 2000)  # just over 85%
        assert policy.should_compress(sample_session, 1800, 2000)  # over 85%
        assert policy.should_compress(sample_session, 2000, 2000)  # at limit


class TestRetryAfterError:
    """Tests for retry_after_error policy."""

    def test_retry_transient_timeout(self, policy):
        """Retry on timeout error."""
        error = InferenceTimeoutError("timeout")
        decision = policy.retry_after_error(error, attempt=1)
        assert decision.action == RetryAction.RETRY_WITH_BACKOFF
        assert decision.backoff_seconds == 1.0
        assert "transient" in decision.reason

    def test_retry_transient_server_error(self, policy):
        """Retry on server error."""
        error = InferenceServerError("500")
        decision = policy.retry_after_error(error, attempt=1)
        assert decision.action == RetryAction.RETRY_WITH_BACKOFF

    def test_no_retry_on_generic_error(self, policy):
        """Don't retry generic exceptions."""
        error = ValueError("some error")
        decision = policy.retry_after_error(error, attempt=1)
        assert decision.action == RetryAction.FAIL
        assert "non-transient" in decision.reason

    def test_no_retry_after_max_attempts(self, policy):
        """Fail after max attempts even for transient errors."""
        error = InferenceTimeoutError("timeout")
        decision = policy.retry_after_error(error, attempt=2)
        assert decision.action == RetryAction.FAIL
        assert "max attempts" in decision.reason

    def test_no_retry_on_third_attempt(self, policy):
        """Fail on attempt 3 (0-indexed: attempt >= 2 means 3rd attempt)."""
        error = InferenceTimeoutError("timeout")
        decision = policy.retry_after_error(error, attempt=3)
        assert decision.action == RetryAction.FAIL


class TestTurnTokenBudget:
    """Tests for turn_token_budget policy."""

    def test_budget_math(self, policy):
        """Budget is 85% of ctx - 2048."""
        budget = policy.turn_token_budget(None)  # type: ignore[arg-type]
        expected = int(32768 * 0.85) - 2048
        assert budget == expected
        assert budget > 0

    def test_custom_ctx_window(self):
        """Custom context window produces correct budget."""
        custom_policy = DefaultPolicyEngine(ctx_window=16384)
        budget = custom_policy.turn_token_budget(None)  # type: ignore[arg-type]
        expected = int(16384 * 0.85) - 2048
        assert budget == expected


class TestDelegation:
    """Tests for delegation policy (Phase 1b: always false)."""

    def test_no_delegation_in_phase_1b(self, policy, sample_session):
        """Delegation is disabled in Phase 1b."""
        assert not policy.should_delegate(sample_session, "any task")
        assert not policy.should_delegate(sample_session, "complex multi-step task")


class TestSlotEviction:
    """Tests for slot eviction policy (Phase 1b: always false)."""

    def test_no_eviction_in_phase_1b(self, policy):
        """Slot eviction is disabled in Phase 1b."""
        assert not policy.should_evict_slot(0, 0.9)
        assert not policy.should_evict_slot(1, 1.0)


class TestToolResultMaxChars:
    """Tests for tool result max chars policy."""

    def test_default_max_chars(self, policy):
        """Default is 8000 chars."""
        assert policy.tool_result_max_chars("any_tool") == 8000
        assert policy.tool_result_max_chars("read_file") == 8000
