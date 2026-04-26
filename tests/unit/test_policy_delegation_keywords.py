"""Tests for policy delegation keywords config."""


from hestia.config import PolicyConfig
from hestia.core.clock import utcnow
from hestia.core.types import Session, SessionState, SessionTemperature
from hestia.policy.default import (
    DEFAULT_DELEGATION_KEYWORDS,
    DEFAULT_RESEARCH_KEYWORDS,
    DefaultPolicyEngine,
)


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


class TestDefaultDelegationKeywords:
    """Test default explicit delegation keyword behavior."""

    def test_default_keywords_used(self):
        """Message containing 'delegate' triggers delegation with defaults."""
        engine = DefaultPolicyEngine()
        session = _make_session()
        assert engine.should_delegate(session, "please delegate this task")

    def test_custom_keywords_override(self):
        """Custom config overrides default explicit delegation keywords."""
        config = PolicyConfig(delegation_keywords=("only_this",))
        engine = DefaultPolicyEngine(config=config)
        session = _make_session()
        assert not engine.should_delegate(session, "please delegate this task")
        assert engine.should_delegate(session, "only_this task")

    def test_empty_tuple_disables_explicit_delegation(self):
        """Empty delegation_keywords tuple disables explicit keyword delegation."""
        config = PolicyConfig(delegation_keywords=())
        engine = DefaultPolicyEngine(config=config)
        session = _make_session()
        assert not engine.should_delegate(session, "delegate this task")
        assert not engine.should_delegate(session, "spawn task for me")
        # Research keywords still work
        assert engine.should_delegate(session, "research this topic")

    def test_none_uses_defaults(self):
        """None config uses default explicit delegation keywords."""
        config = PolicyConfig(delegation_keywords=None)
        engine = DefaultPolicyEngine(config=config)
        session = _make_session()
        assert engine.should_delegate(session, "delegate")


class TestDefaultDelegationKeywordsConstant:
    """Test the DEFAULT_DELEGATION_KEYWORDS constant."""

    def test_constant_values(self):
        """Default explicit delegation keywords match expected values."""
        assert "delegate" in DEFAULT_DELEGATION_KEYWORDS
        assert "subagent" in DEFAULT_DELEGATION_KEYWORDS
        assert "spawn task" in DEFAULT_DELEGATION_KEYWORDS
        assert "background task" in DEFAULT_DELEGATION_KEYWORDS


class TestDefaultResearchKeywordsConstant:
    """Test the DEFAULT_RESEARCH_KEYWORDS constant."""

    def test_constant_values(self):
        """Default research keywords match expected values."""
        assert "research" in DEFAULT_RESEARCH_KEYWORDS
        assert "investigate" in DEFAULT_RESEARCH_KEYWORDS
        assert "analyze deeply" in DEFAULT_RESEARCH_KEYWORDS
        assert "comprehensive" in DEFAULT_RESEARCH_KEYWORDS
