"""Validation helpers for Hestia configuration."""

from __future__ import annotations

import os


def validate_inference_model_name(model_name: str) -> None:
    """Reject the reserved ``dummy`` model name unless explicitly allowed.

    The literal ``dummy`` is used only in tests behind ``HESTIA_ALLOW_DUMMY_MODEL=1``.
    """
    stripped = model_name.strip()
    if stripped.lower() != "dummy":
        return
    if os.environ.get("HESTIA_ALLOW_DUMMY_MODEL") == "1":
        return
    raise ValueError(
        'inference.model_name "dummy" is reserved for automated tests only. '
        "Configure a real llama.cpp model filename, or set environment variable "
        "HESTIA_ALLOW_DUMMY_MODEL=1 if you intentionally use a dummy model."
    )
