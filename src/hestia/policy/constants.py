"""Shared policy tuning constants."""

from typing import Final, Literal

# Fraction of per-turn token budget above which compression is triggered
# (``DefaultPolicyEngine.should_compress`` and related CLI messaging).
CONTEXT_PRESSURE_THRESHOLD: Final[float] = 0.85

# Reserved ``Session.platform`` value for subagent / delegate_task sessions.
# Policy uses this to avoid recursive delegation.
PLATFORM_SUBAGENT: Final[Literal["subagent"]] = "subagent"
