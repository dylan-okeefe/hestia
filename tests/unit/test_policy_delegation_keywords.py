"""Tests for policy delegation keywords config."""

import pytest

from hestia.config import PolicyConfig
from hestia.core.types import Session, SessionState, SessionTemperature
from hestia.policy.default import DEFAULT_DELEGATION_KEYWORDS, DefaultPolicyEngine
from hestia.core.clock import utcnow


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
    """Test default delegation keyword behavior."""

    def test_default_keywords_used(self):
        """Message containing 'research' triggers delegation with defaults."""
        engine = DefaultPolicyEngine()
        session = _make_session()
        assert engine.should_delegate(session, "I'd like to research my family history")

    def test_custom_keywords_override(self):
        """Custom config overrides default keywords."""
        config = PolicyConfig(delegation_keywords=("only_this",))
        engine = DefaultPolicyEngine(config=config)
        session = _make_session()
        assert not engine.should_delegate(session, "I'd like to research my family history")
        assert engine.should_delegate(session, "only_this task")

    def test_empty_tuple_disables_keyword_delegation(self):
        """Empty delegation_keywords tuple disables keyword-based delegation."""
        config = PolicyConfig(delegation_keywords=())
        engine = DefaultPolicyEngine(config=config)
        session = _make_session()
        assert not engine.should_delegate(session, "research this topic")
        assert not engine.should_delegate(session, "investigate that issue")
        assert not engine.should_delegate(session, "analyze deeply")
        assert not engine.should_delegate(session, "comprehensive review")
        # Other triggers still work
        assert engine.should_delegate(session, "delegate this task")

    def test_none_uses_defaults(self):
        """None config uses default keywords."""
        config = PolicyConfig(delegation_keywords=None)
        engine = DefaultPolicyEngine(config=config)
        session = _make_session()
        assert engine.should_delegate(session, "research")


class TestDefaultDelegationKeywordsConstant:
    """Test the DEFAULT_DELEGATION_KEYWORDS constant."""

    def test_constant_values(self):
        """Default keywords match expected values."""
        assert "research" in DEFAULT_DELEGATION_KEYWORDS
        assert "investigate" in DEFAULT_DELEGATION_KEYWORDS
        assert "analyze deeply" in DEFAULT_DELEGATION_KEYWORDS
        assert "comprehensive" in DEFAULT_DELEGATION_KEYWORDS
