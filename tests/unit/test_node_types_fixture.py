"""D7 backend half: the committed fixture matches NODE_TYPES exactly."""

from __future__ import annotations

import json
from pathlib import Path

from hestia.workflows.nodes import NODE_TYPES

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "web-ui" / "src" / "generated" / "node-types.json"
)


def test_fixture_matches_node_types() -> None:
    assert json.loads(FIXTURE.read_text()) == sorted(NODE_TYPES.keys()), (
        "node-types.json has drifted from NODE_TYPES - regenerate via "
        "`uv run python -c \"…\"` documented in the register (D7)."
    )
