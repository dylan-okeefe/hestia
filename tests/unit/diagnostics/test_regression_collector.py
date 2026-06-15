"""Tests for the regression fixture collector."""

import json
import os
import tempfile

from hestia.core.types import Message, ToolCall
from hestia.diagnostics import regression_collector


class TestRegressionCollector:
    """Regression collector is opt-in via HESTIA_REGRESSION_FIXTURES_DIR."""

    def test_no_op_when_env_var_unset(self):
        """When the env var is not set, nothing is written."""
        os.environ.pop("HESTIA_REGRESSION_FIXTURES_DIR", None)
        path = regression_collector.maybe_collect_malformed_tool_call(
            "write_file", "not-a-dict"
        )
        assert path is None

    def test_collects_malformed_tool_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["HESTIA_REGRESSION_FIXTURES_DIR"] = tmp
            path = regression_collector.maybe_collect_malformed_tool_call(
                "write_file", "not-a-dict"
            )
            assert path is not None
            assert path.parent.name == "malformed_tool_calls"
            data = json.loads(path.read_text())
            assert data["tool_name"] == "write_file"
            assert data["raw_arguments"] == "not-a-dict"

    def test_collects_tool_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["HESTIA_REGRESSION_FIXTURES_DIR"] = tmp
            path = regression_collector.maybe_collect_tool_failure(
                "browser_get_links",
                {"url": "https://example.com"},
                "Error fetching: Timeout 30000ms exceeded.",
            )
            assert path is not None
            assert path.parent.name == "tool_failures"
            data = json.loads(path.read_text())
            assert data["tool_name"] == "browser_get_links"
            assert data["arguments"]["url"] == "https://example.com"

    def test_collects_degenerate_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["HESTIA_REGRESSION_FIXTURES_DIR"] = tmp
            history = [
                Message(role="assistant", content="", tool_calls=[
                    ToolCall(id="tc1", name="list_tools", arguments={})
                ]),
                Message(role="tool", content="...", tool_call_id="tc1"),
            ]
            path = regression_collector.maybe_collect_degenerate_turn(
                "repeated_list_tools",
                history,
            )
            assert path is not None
            assert path.parent.name == "degenerate_turns"
            data = json.loads(path.read_text())
            assert data["correction"] == "repeated_list_tools"
            assert len(data["history"]) == 2
