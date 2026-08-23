"""Shared test fakes for the L245 gate chokepoint.

Review finding 1: an unbound registry refuses enforce-mode calls, so any
test that wants "no policy" must bind a visible permissive fake instead of
relying on the old silent passthrough.
"""

from __future__ import annotations

from hestia.policy.gate import CapabilityResult


class PermissiveGate:
    """Allows every tool; evaluates nothing. For tests that exercise
    dispatch mechanics rather than authorization."""

    async def check(
        self,
        request,  # noqa: ANN001 - test fake, signature mirrors CapabilityGate.check
        *,
        injection_flagged: bool = False,
        allow_list: set[str] | None = None,
    ) -> CapabilityResult:
        return CapabilityResult(
            allowed=True,
            auto_approved=True,
            requires_confirmation=False,
            reason="permissive-test-fake",
        )


def bind_permissive_gate(registry) -> None:  # noqa: ANN001 - ToolRegistry
    """Bind :class:`PermissiveGate` to *registry* (test wiring helper)."""
    registry.bind_gate(PermissiveGate())
