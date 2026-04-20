"""Regression test for PolicyEngine.ctx_window contract (Copilot A-3).

Callsites such as ``src/hestia/commands.py`` access
``policy.ctx_window`` directly after receiving a PolicyEngine handle.
Before v0.9.0 the attribute was declared only on
:class:`~hestia.policy.default.DefaultPolicyEngine`, so a third-party
subclass of :class:`~hestia.policy.engine.PolicyEngine` that did not
inherit from ``DefaultPolicyEngine`` would raise ``AttributeError`` at
runtime the first time ``hestia policy show`` was called.

The fix documents ``ctx_window: int`` on the ABC so type checkers enforce
it and subclass authors can't silently miss it. This test locks that
contract by:

- Constructing a minimal ``PolicyEngine`` subclass that implements every
  abstract method but assigns ``self.ctx_window`` in ``__init__``, and
  confirms the attribute is readable and returns the assigned value.
- Confirming the attribute is declared on the ABC itself (so future
  refactors that drop the annotation fail this test instead of silently
  regressing).
"""

from __future__ import annotations

from hestia.core.types import Session
from hestia.policy.engine import PolicyEngine, RetryAction, RetryDecision


class _MinimalPolicyEngine(PolicyEngine):
    """Subclass used by the ctx_window contract test — no behavior."""

    def __init__(self, ctx_window: int) -> None:
        self.ctx_window = ctx_window

    def should_delegate(
        self,
        session: Session,
        task_description: str,
        tool_chain_length: int = 0,
        projected_tool_calls: int = 0,
    ) -> bool:
        return False

    def should_compress(self, session, tokens_used: int, tokens_budget: int) -> bool:
        return False

    def retry_after_error(self, error: Exception, attempt: int) -> RetryDecision:
        return RetryDecision(action=RetryAction.FAIL, reason="minimal")

    def turn_token_budget(self, session) -> int:
        return self.ctx_window

    def tool_result_max_chars(self, tool_name: str) -> int:
        return 1024

    def filter_tools(self, session, tool_names, registry):
        return tool_names

    def auto_approve(self, tool_name: str, session) -> bool:
        return False

    def reasoning_budget(self, session, iteration: int) -> int:
        return 512


def test_ctx_window_declared_on_abc() -> None:
    """``PolicyEngine`` annotates ``ctx_window: int`` so subclasses see it."""
    assert "ctx_window" in PolicyEngine.__annotations__
    assert PolicyEngine.__annotations__["ctx_window"] is int


def test_minimal_subclass_can_expose_ctx_window() -> None:
    """A PolicyEngine subclass that sets ctx_window in __init__ is usable."""
    policy = _MinimalPolicyEngine(ctx_window=4096)
    assert policy.ctx_window == 4096
    # And the value is reachable via the dynamic attribute access path used
    # by commands.py (`policy.ctx_window`), not just via subclass lookup.
    assert getattr(policy, "ctx_window") == 4096
