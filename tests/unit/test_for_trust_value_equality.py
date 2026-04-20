"""Regression test: for_trust must use value equality, not identity."""

from hestia.config import HestiaConfig, TrustConfig


def test_for_trust_dispatches_after_value_recreation():
    """JSON round-trips create new objects with the same values.

    ``for_trust`` must rely on value equality (``==``) so that a
    ``TrustConfig`` reconstructed from JSON still dispatches to the
    correct handoff/compression preset.
    """
    cfg = HestiaConfig.for_trust(TrustConfig.household())
    # Simulate a JSON round-trip: same field values, different identity.
    revived = TrustConfig(
        auto_approve_tools=["terminal", "write_file"],
        scheduler_shell_exec=True,
        subagent_shell_exec=True,
        subagent_write_local=True,
    )
    assert revived is not cfg.trust
    assert revived == cfg.trust
    cfg2 = HestiaConfig.for_trust(revived)
    assert cfg2.trust == cfg.trust
    assert cfg2.handoff.enabled == cfg.handoff.enabled
    assert cfg2.compression.enabled == cfg.compression.enabled
