"""Pytest configuration for the whole test tree.

H-5 (Copilot): ``model_name == "dummy"`` is rejected unless
``HESTIA_ALLOW_DUMMY_MODEL=1``. Many unit tests build ``AppContext`` via
``make_app`` with an empty ``inference.model_name``; the app layer maps that to
``dummy`` only when this env is set so ``InferenceClient`` construction succeeds.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _allow_dummy_model_for_tests() -> None:
    os.environ.setdefault("HESTIA_ALLOW_DUMMY_MODEL", "1")
