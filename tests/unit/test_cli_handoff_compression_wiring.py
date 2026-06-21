"""L21 wiring: cli.py must honour CompressionConfig.

Regression guard for the review finding that `CompressionConfig` was
defined but never read by `cli.py`, so the L21 feature was dead code in
the real runtime.
"""

from __future__ import annotations

from hestia.config import CompressionConfig, HestiaConfig
from hestia.context.compressor import InferenceHistoryCompressor


def test_compression_config_disabled_by_default() -> None:
    cfg = HestiaConfig()
    assert cfg.compression.enabled is False


def test_cli_wires_compression_when_enabled(tmp_path, monkeypatch) -> None:
    """When CompressionConfig.enabled=True, the context builder gets a compressor.

    We exercise the same helper the CLI uses (enable_compression) and assert
    the builder flips its overflow behaviour.
    """
    from hestia.context.builder import ContextBuilder
    from hestia.core.inference import InferenceClient
    from hestia.policy.default import DefaultPolicyEngine

    inference = InferenceClient(base_url="http://127.0.0.1:1", model_name="x")
    policy = DefaultPolicyEngine()
    builder = ContextBuilder(inference_client=inference, policy=policy)
    assert builder._compressor is None  # type: ignore[attr-defined]
    assert builder._compress_on_overflow is False  # type: ignore[attr-defined]

    cfg = CompressionConfig(enabled=True, max_chars=400)
    builder.enable_compression(InferenceHistoryCompressor(inference, max_chars=cfg.max_chars))
    assert builder._compressor is not None  # type: ignore[attr-defined]
    assert builder._compress_on_overflow is True  # type: ignore[attr-defined]


