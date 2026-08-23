"""Caller identity carried alongside every tool invocation.

L245 chokepoint: ``ToolRegistry.call`` requires one of these so that an
ungated tool call is not expressible — the registry itself evaluates the
CapabilityGate (mode="enforce") or trusts a decision the orchestrator
already made for exactly this tool (mode="pre_gated", single-evaluation
criterion, bound to the tool name so a decision cannot be replayed for a
different invocation).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hestia.policy.channel import Channel
from hestia.policy.gate import CapabilityResult


@dataclass(frozen=True)
class ToolCallContext:
    """Who is invoking a tool, from where, under which authorization."""

    channel: Channel
    actor_platform: str = "system"
    actor_platform_user: str = "internal"
    session_id: str | None = None
    allow_list: frozenset[str] = frozenset()
    source_workflow_id: str | None = None
    injection_flagged: bool = False
    mode: str = "enforce"  # "enforce" | "pre_gated"
    pre_gated_result: CapabilityResult | None = field(default=None)
    pre_gated_tool: str | None = None

    def __post_init__(self) -> None:
        if self.mode not in ("enforce", "pre_gated"):
            raise ValueError(f"Unknown ToolCallContext mode: {self.mode!r}")
        if self.mode == "pre_gated":
            if self.pre_gated_result is None:
                raise ValueError("pre_gated mode requires pre_gated_result")
            if not self.pre_gated_tool:
                raise ValueError(
                    "pre_gated mode requires pre_gated_tool - a decision is "
                    "only valid for the tool it was made for"
                )
