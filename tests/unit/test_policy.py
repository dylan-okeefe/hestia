"""Unit tests for PolicyEngine."""

import pytest

from hestia.config import StorageConfig
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

    def test_retry_empty_response(self, policy):
        """Retry on empty model response."""
        from hestia.errors import EmptyResponseError
        error = EmptyResponseError("empty")
        decision = policy.retry_after_error(error, attempt=1)
        assert decision.action == RetryAction.RETRY
        assert "empty" in decision.reason

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
    """Tests for should_delegate policy."""

    def test_no_delegation_for_benign_tasks(self, policy, sample_session):
        """Ordinary tasks do not trigger delegation heuristics."""
        assert not policy.should_delegate(sample_session, "any task")
        assert not policy.should_delegate(sample_session, "hello")

    def test_delegation_keywords(self, policy, sample_session):
        """User can ask explicitly for delegation."""
        assert policy.should_delegate(sample_session, "use a subagent for this")
        assert policy.should_delegate(sample_session, "please delegate this task")

    def test_subagent_session_never_delegates(self, policy, sample_session):
        """Avoid recursive policy delegation inside subagent turns."""
        from dataclasses import replace

        sub = replace(sample_session, platform="subagent")
        assert not policy.should_delegate(
            sub,
            "delegate everything to a subagent",
            tool_chain_length=99,
            projected_tool_calls=9,
        )


class TestToolResultMaxChars:
    """Tests for tool result max chars policy."""

    def test_default_max_chars(self, policy):
        """Default is 8000 chars."""
        assert policy.tool_result_max_chars("any_tool") == 8000
        assert policy.tool_result_max_chars("read_file") == 8000


class TestFilterTools:
    """Tests for capability-based tool filtering."""

    def test_subagent_blocks_shell_and_write(self, policy, sample_session, tmp_path):
        from dataclasses import replace

        from hestia.artifacts.store import ArtifactStore
        from hestia.tools.builtin import current_time, make_write_file_tool, terminal
        from hestia.tools.registry import ToolRegistry

        reg = ToolRegistry(ArtifactStore(tmp_path / "art"))
        reg.register(current_time)
        reg.register(terminal)
        reg.register(make_write_file_tool(StorageConfig(allowed_roots=[str(tmp_path)])))
        names = reg.list_names()
        sub = replace(sample_session, platform="subagent")
        filtered = policy.filter_tools(sub, names, reg)
        assert "terminal" not in filtered
        assert "write_file" not in filtered
        assert "current_time" in filtered

    def test_scheduler_tick_blocks_shell(self, policy, sample_session, tmp_path):
        from hestia.artifacts.store import ArtifactStore
        from hestia.runtime_context import scheduler_tick_active
        from hestia.tools.builtin import current_time, terminal
        from hestia.tools.registry import ToolRegistry

        reg = ToolRegistry(ArtifactStore(tmp_path / "art"))
        reg.register(current_time)
        reg.register(terminal)
        names = reg.list_names()
        token = scheduler_tick_active.set(True)
        try:
            filtered = policy.filter_tools(sample_session, names, reg)
        finally:
            scheduler_tick_active.reset(token)
        assert "terminal" not in filtered
        assert "current_time" in filtered

    def test_cli_allows_terminal(self, policy, sample_session, tmp_path):
        from hestia.artifacts.store import ArtifactStore
        from hestia.tools.builtin import current_time, terminal
        from hestia.tools.registry import ToolRegistry

        reg = ToolRegistry(ArtifactStore(tmp_path / "art"))
        reg.register(current_time)
        reg.register(terminal)
        names = reg.list_names()
        cli_sess = sample_session  # platform "test" is not subagent/scheduler
        filtered = policy.filter_tools(cli_sess, names, reg)
        assert filtered == names


class TestAutoApprove:
    """Tests for auto_approve policy."""

    def test_paranoid_denies_all(self, sample_session):
        from hestia.config import TrustConfig
        from hestia.policy.default import DefaultPolicyEngine

        policy = DefaultPolicyEngine(trust=TrustConfig.paranoid())
        assert not policy.auto_approve("terminal", sample_session)
        assert not policy.auto_approve("write_file", sample_session)
        assert not policy.auto_approve("any_tool", sample_session)

    def test_household_approves_terminal_and_write_file(self, sample_session):
        from hestia.config import TrustConfig
        from hestia.policy.default import DefaultPolicyEngine

        policy = DefaultPolicyEngine(trust=TrustConfig.household())
        assert policy.auto_approve("terminal", sample_session)
        assert policy.auto_approve("write_file", sample_session)
        assert not policy.auto_approve("some_other_tool", sample_session)

    def test_developer_approves_wildcard(self, sample_session):
        from hestia.config import TrustConfig
        from hestia.policy.default import DefaultPolicyEngine

        policy = DefaultPolicyEngine(trust=TrustConfig.developer())
        assert policy.auto_approve("any_tool_name", sample_session)
        assert policy.auto_approve("terminal", sample_session)


class TestFilterToolsTrust:
    """Tests for filter_tools with TrustConfig."""

    def test_subagent_paranoid_blocks_shell_and_write(self, sample_session, tmp_path):
        from dataclasses import replace

        from hestia.artifacts.store import ArtifactStore
        from hestia.config import TrustConfig
        from hestia.policy.default import DefaultPolicyEngine
        from hestia.tools.builtin import current_time, make_write_file_tool, terminal
        from hestia.tools.registry import ToolRegistry

        policy = DefaultPolicyEngine(trust=TrustConfig.paranoid())
        reg = ToolRegistry(ArtifactStore(tmp_path / "art"))
        reg.register(current_time)
        reg.register(terminal)
        reg.register(make_write_file_tool(StorageConfig(allowed_roots=[str(tmp_path)])))
        names = reg.list_names()
        sub = replace(sample_session, platform="subagent")
        filtered = policy.filter_tools(sub, names, reg)
        assert "terminal" not in filtered
        assert "write_file" not in filtered
        assert "current_time" in filtered

    def test_subagent_household_allows_all(self, sample_session, tmp_path):
        from dataclasses import replace

        from hestia.artifacts.store import ArtifactStore
        from hestia.config import TrustConfig
        from hestia.policy.default import DefaultPolicyEngine
        from hestia.tools.builtin import current_time, make_write_file_tool, terminal
        from hestia.tools.registry import ToolRegistry

        policy = DefaultPolicyEngine(trust=TrustConfig.household())
        reg = ToolRegistry(ArtifactStore(tmp_path / "art"))
        reg.register(current_time)
        reg.register(terminal)
        reg.register(make_write_file_tool(StorageConfig(allowed_roots=[str(tmp_path)])))
        names = reg.list_names()
        sub = replace(sample_session, platform="subagent")
        filtered = policy.filter_tools(sub, names, reg)
        assert "terminal" in filtered
        assert "write_file" in filtered
        assert "current_time" in filtered

    def test_subagent_partial_config(self, sample_session, tmp_path):
        from dataclasses import replace

        from hestia.artifacts.store import ArtifactStore
        from hestia.config import TrustConfig
        from hestia.policy.default import DefaultPolicyEngine
        from hestia.tools.builtin import current_time, make_write_file_tool, terminal
        from hestia.tools.registry import ToolRegistry

        trust = TrustConfig(subagent_shell_exec=True, subagent_write_local=False)
        policy = DefaultPolicyEngine(trust=trust)
        reg = ToolRegistry(ArtifactStore(tmp_path / "art"))
        reg.register(current_time)
        reg.register(terminal)
        reg.register(make_write_file_tool(StorageConfig(allowed_roots=[str(tmp_path)])))
        names = reg.list_names()
        sub = replace(sample_session, platform="subagent")
        filtered = policy.filter_tools(sub, names, reg)
        assert "terminal" in filtered
        assert "write_file" not in filtered
        assert "current_time" in filtered

    def test_scheduler_paranoid_blocks_shell(self, sample_session, tmp_path):
        from hestia.artifacts.store import ArtifactStore
        from hestia.config import TrustConfig
        from hestia.policy.default import DefaultPolicyEngine
        from hestia.tools.builtin import current_time, terminal
        from hestia.tools.registry import ToolRegistry

        policy = DefaultPolicyEngine(trust=TrustConfig.paranoid())
        reg = ToolRegistry(ArtifactStore(tmp_path / "art"))
        reg.register(current_time)
        reg.register(terminal)
        names = reg.list_names()
        sched = sample_session
        sched.platform = "scheduler"
        filtered = policy.filter_tools(sched, names, reg)
        assert "terminal" not in filtered
        assert "current_time" in filtered

    def test_scheduler_household_allows_shell(self, sample_session, tmp_path):
        from hestia.artifacts.store import ArtifactStore
        from hestia.config import TrustConfig
        from hestia.policy.default import DefaultPolicyEngine
        from hestia.tools.builtin import current_time, terminal
        from hestia.tools.registry import ToolRegistry

        policy = DefaultPolicyEngine(trust=TrustConfig.household())
        reg = ToolRegistry(ArtifactStore(tmp_path / "art"))
        reg.register(current_time)
        reg.register(terminal)
        names = reg.list_names()
        sched = sample_session
        sched.platform = "scheduler"
        filtered = policy.filter_tools(sched, names, reg)
        assert "terminal" in filtered
        assert "current_time" in filtered


class TestReasoningBudget:
    """Tests for reasoning_budget policy."""

    def test_default_reasoning_budget(self, policy):
        """Default reasoning budget is 2048."""
        budget = policy.reasoning_budget(None, 0)  # type: ignore[arg-type]
        assert budget == 2048

    def test_custom_default_reasoning_budget(self):
        """Custom default reasoning budget is respected."""
        custom_policy = DefaultPolicyEngine(default_reasoning_budget=4096)
        budget = custom_policy.reasoning_budget(None, 0)  # type: ignore[arg-type]
        assert budget == 4096

    def test_subagent_gets_smaller_budget(self, sample_session):
        """Subagent sessions get capped at 1024 tokens."""
        from dataclasses import replace

        policy = DefaultPolicyEngine(default_reasoning_budget=2048)
        subagent_session = replace(sample_session, platform="subagent")

        budget = policy.reasoning_budget(subagent_session, 0)
        assert budget == 1024

    def test_subagent_budget_capped_even_with_high_default(self, sample_session):
        """Subagent budget is capped at 1024 even with high default."""
        from dataclasses import replace

        policy = DefaultPolicyEngine(default_reasoning_budget=8192)
        subagent_session = replace(sample_session, platform="subagent")

        budget = policy.reasoning_budget(subagent_session, 0)
        assert budget == 1024

    def test_non_subagent_gets_full_budget(self, sample_session):
        """Non-subagent sessions get the full default budget."""
        policy = DefaultPolicyEngine(default_reasoning_budget=4096)

        budget = policy.reasoning_budget(sample_session, 0)
        assert budget == 4096

    def test_iteration_parameter_ignored_for_now(self, sample_session):
        """Iteration parameter doesn't affect budget (reserved for future)."""
        policy = DefaultPolicyEngine(default_reasoning_budget=2048)

        budget_first = policy.reasoning_budget(sample_session, 0)
        budget_second = policy.reasoning_budget(sample_session, 1)
        budget_tenth = policy.reasoning_budget(sample_session, 9)

        assert budget_first == budget_second == budget_tenth == 2048


class TestCtxWindowWiring:
    """Tests for ctx_window default and config wiring."""

    def test_ctx_window_default_is_8k(self):
        """DefaultPolicyEngine ctx_window defaults to 8192."""
        policy = DefaultPolicyEngine()
        assert policy.ctx_window == 8192

    def test_turn_token_budget_uses_ctx_window(self):
        """Budget reflects the configured ctx_window ceiling."""
        policy = DefaultPolicyEngine(ctx_window=8192)
        budget = policy.turn_token_budget(None)  # type: ignore[arg-type]
        expected = int(8192 * 0.85) - 2048
        assert budget == expected
        assert budget > 0

    def test_cli_passes_ctx_window_from_config(self):
        """_make_policy wires HestiaConfig.inference.context_length into the engine."""
        from hestia.app import _make_policy
        from hestia.config import HestiaConfig, InferenceConfig

        cfg = HestiaConfig(inference=InferenceConfig(context_length=32768))
        policy = _make_policy(cfg)
        assert policy.ctx_window == 32768
