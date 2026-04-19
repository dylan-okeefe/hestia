"""Tests for policy research keywords config."""

from hestia.config import PolicyConfig
from hestia.core.clock import utcnow
from hestia.core.types import Session, SessionState, SessionTemperature
from hestia.policy.default import DefaultPolicyEngine


def _make_session() -> Session:
    return Session(
        id="test",
        platform="cli",
        platform_user="user",
        started_at=utcnow(),
        last_active_at=utcnow(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.HOT,
    )


class TestDefaultResearchKeywords:
    """Test default research keyword behavior."""

    def test_default_research_keywords_used(self):
        """Message containing 'investigate' triggers delegation via research keywords."""
        engine = DefaultPolicyEngine()
        session = _make_session()
        assert engine.should_delegate(
            session, "investigate this issue", projected_tool_calls=1
        )

    def test_custom_research_keywords_override(self):
        """Custom research_keywords overrides default research keywords."""
        config = PolicyConfig(research_keywords=("only_this",))
        engine = DefaultPolicyEngine(config=config)
        session = _make_session()
        assert not engine.should_delegate(
            session, "investigate this issue", projected_tool_calls=1
        )
        assert engine.should_delegate(
            session, "only_this task", projected_tool_calls=1
        )

    def test_empty_research_keywords_disables(self):
        """Empty research_keywords tuple disables research keyword delegation."""
        config = PolicyConfig(research_keywords=())
        engine = DefaultPolicyEngine(config=config)
        session = _make_session()
        assert not engine.should_delegate(
            session, "research this topic", projected_tool_calls=1
        )
        assert not engine.should_delegate(
            session, "investigate that issue", projected_tool_calls=1
        )
        assert not engine.should_delegate(
            session, "analyze deeply", projected_tool_calls=1
        )
        assert not engine.should_delegate(
            session, "comprehensive review", projected_tool_calls=1
        )

    def test_delegation_and_research_independent(self):
        """delegation_keywords=() does not disable research keyword path, and vice versa."""
        session = _make_session()

        config = PolicyConfig(delegation_keywords=())
        engine = DefaultPolicyEngine(config=config)
        # Explicit delegation keywords disabled, but research still works
        assert not engine.should_delegate(session, "delegate this task")
        assert engine.should_delegate(
            session, "research this topic", projected_tool_calls=1
        )

        config2 = PolicyConfig(research_keywords=())
        engine2 = DefaultPolicyEngine(config=config2)
        # Research keywords disabled, but explicit delegation still works
        assert not engine2.should_delegate(
            session, "research this topic", projected_tool_calls=1
        )
        assert engine2.should_delegate(session, "delegate this task")
