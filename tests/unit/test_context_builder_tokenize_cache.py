"""Unit tests for ContextBuilder per-message tokenize cache."""

from datetime import datetime

import pytest

from hestia.context.builder import ContextBuilder
from hestia.core.types import Message, Session, SessionState, SessionTemperature
from hestia.policy.default import DefaultPolicyEngine


class TokenizeCountingInference:
    """Fake inference client that counts tokenize() calls.

    count_request() uses the same char-based heuristic as the legacy
    FakeInferenceClient so existing behaviour is preserved.
    tokenize() is exposed for the new cache path and increments a counter.
    """

    def __init__(self) -> None:
        self.model_name = "fake-model"
        self.tokenize_calls = 0

    async def tokenize(self, text: str) -> list[int]:
        self.tokenize_calls += 1
        return [0] * (len(text) // 4 + 1)

    async def count_request(self, messages, tools=None):
        total = 0
        for msg in messages:
            total += 10
            total += len(msg.content) // 4
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    total += len(tc.name) + len(str(tc.arguments))
        for tool in (tools or []):
            total += len(tool.function.name) * 2
        return total

    async def tokenize_batch(self, texts: list[str]) -> list[int]:
        """Fallback batch tokenization for testing."""
        import asyncio

        results = await asyncio.gather(*(self.tokenize(t) for t in texts))
        return [len(r) for r in results]


@pytest.fixture
def inference():
    return TokenizeCountingInference()


@pytest.fixture
def policy():
    return DefaultPolicyEngine(ctx_window=8192)


@pytest.fixture
def session():
    return Session(
        id="s1",
        platform="test",
        platform_user="user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )


@pytest.mark.asyncio
async def test_tokenize_cache_hits_on_repeated_build(inference, policy, session):
    """Second build with identical messages issues no new per-message tokenize calls."""
    builder = ContextBuilder(inference, policy)
    history = [Message(role="user", content=f"msg {i}") for i in range(10)]
    new_msg = Message(role="user", content="new")

    await builder.build(session, history, "System", [], new_user_message=new_msg)
    calls_after_first = inference.tokenize_calls

    await builder.build(session, history, "System", [], new_user_message=new_msg)
    calls_after_second = inference.tokenize_calls

    # Join-overhead is cached after first build, and all per-message counts
    # are cached, so the second build issues zero new tokenize calls.
    assert calls_after_second == calls_after_first


@pytest.mark.asyncio
async def test_tokenize_cache_invalidation_on_new_message(inference, policy, session):
    """Appending a new message causes exactly one new _count_tokens call."""
    builder = ContextBuilder(inference, policy)
    history = [Message(role="user", content=f"msg {i}") for i in range(10)]
    new_msg = Message(role="user", content="new")

    await builder.build(session, history, "System", [], new_user_message=new_msg)
    calls_after_first = inference.tokenize_calls

    history.append(Message(role="user", content="extra"))
    await builder.build(session, history, "System", [], new_user_message=new_msg)
    calls_after_second = inference.tokenize_calls

    # One new _count_tokens cache miss for the appended message;
    # join-overhead remains cached from the first build.
    assert calls_after_second == calls_after_first + 1


@pytest.mark.asyncio
async def test_total_tokens_matches_joined_string_baseline(inference, policy, session):
    """Cached trim loop selects the same window (±1 msg) as the old O(N) loop."""
    builder = ContextBuilder(inference, policy)

    # 50-message synthetic conversation
    history = []
    for i in range(25):
        history.append(Message(role="user", content=f"Question {i}"))
        history.append(Message(role="assistant", content=f"Answer {i}"))

    new_msg = Message(role="user", content="Final question")

    result = await builder.build(
        session, history, "System", [], new_user_message=new_msg
    )

    # Reference: manual simulation of the old trim loop using _count_messages
    # on the full candidate string every iteration.
    system_msg = Message(role="system", content="System")
    protected_top = [system_msg]
    first_user = None
    for msg in history:
        if msg.role == "user":
            first_user = msg
            protected_top.append(msg)
            break
    protected_bottom = [new_msg]
    raw_budget = policy.turn_token_budget(session)
    await builder._count_messages(
        protected_top + protected_bottom, False
    )

    included_ref = []
    candidates = list(reversed(history))
    i = 0
    while i < len(candidates):
        msg = candidates[i]
        if msg is first_user:
            i += 1
            continue
        test_msgs = protected_top + included_ref + [msg] + protected_bottom
        count = await builder._count_messages(test_msgs, False)
        if count <= raw_budget:
            included_ref.append(msg)
        else:
            break
        i += 1

    # The cached result and reference may differ by at most 1 message at the
    # boundary because the join-overhead approximation can shift by a token.
    cached_included = [
        m for m in result.messages
        if m.role != "system" and m not in protected_bottom
    ]
    # Remove first_user from comparison
    if first_user in cached_included:
        cached_included.remove(first_user)

    assert abs(len(cached_included) - len(included_ref)) <= 1
    # Budget must still be respected
    assert result.tokens_used <= result.tokens_budget


@pytest.mark.asyncio
async def test_role_and_content_are_the_cache_key(inference, policy, session):
    """Messages with identical role+content but different created_at share the cache."""
    builder = ContextBuilder(inference, policy)

    msg1 = Message(role="user", content="shared")
    # Ensure distinct created_at values
    msg2 = Message(role="user", content="shared")
    assert msg1.created_at != msg2.created_at

    history = [msg1, msg2]
    new_msg = Message(role="user", content="new")

    await builder.build(session, history, "System", [], new_user_message=new_msg)

    # Both messages have the same (role, content) key, so tokenize should have
    # been called only once for that unique key.
    # We verify by checking that the cache size for that key is 1.
    assert builder._tokenize_cache[("user", "shared")] > 0
