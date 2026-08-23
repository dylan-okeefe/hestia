"""L245 chunk H: allow-list derivation from the workflow node graph.

The stored ``allow_listed_tools`` set is the authorization a workflow
activation grants. It must be *derived* from the graph - never hand-edited
by the client - so save/activate compute it with these functions.
"""

from __future__ import annotations

import json

from hestia.workflows.models import WorkflowNode
from hestia.workflows.tool_selection import (
    NODE_EFFECT_MARKERS,
    derive_allowed_set,
    derive_allowed_set_from_json,
)


def _node(type_: str, config: dict | None = None) -> WorkflowNode:
    return WorkflowNode(id=f"n-{type_}", type=type_, label="", config=config or {})


class TestDeriveAllowedSet:
    def test_tool_call_nodes_contribute_tool_names(self) -> None:
        nodes = [
            _node("tool_call", {"tool_name": "terminal"}),
            _node("tool_call", {"tool_name": "read_file"}),
        ]
        assert derive_allowed_set(nodes) == {"terminal", "read_file"}

    def test_tool_call_with_missing_name_contributes_nothing(self) -> None:
        assert derive_allowed_set([_node("tool_call", {})]) == set()
        assert derive_allowed_set([_node("tool_call", {"tool_name": 42})]) == set()

    def test_investigate_string_config_parsed(self) -> None:
        nodes = [_node("investigate", {"tools": "search_web, read_file"})]
        assert derive_allowed_set(nodes) == {"search_web", "read_file"}

    def test_investigate_list_config_parsed(self) -> None:
        nodes = [_node("investigate", {"tools": ["web_search", "terminal"]})]
        assert derive_allowed_set(nodes) == {"web_search", "terminal"}

    def test_investigate_malformed_config_fails_closed(self) -> None:
        """A dict-shaped tools value authorizes nothing (and would fail at
        execution time via resolve_invoked_tools)."""
        nodes = [_node("investigate", {"tools": {"web_search": True}})]
        assert derive_allowed_set(nodes) == set()

    def test_effect_nodes_contribute_markers(self) -> None:
        nodes = [
            _node("http_request", {"url": "https://example.com"}),
            _node("send_message", {}),
        ]
        assert derive_allowed_set(nodes) == {
            NODE_EFFECT_MARKERS["http_request"],
            NODE_EFFECT_MARKERS["send_message"],
        }

    def test_unknown_and_structural_node_types_ignored(self) -> None:
        nodes = [
            _node("inference"),
            _node("condition", {"expression": "true"}),
            _node("llm_decision"),
            _node("mystery_type"),
        ]
        assert derive_allowed_set(nodes) == set()

    def test_combined_graph(self) -> None:
        nodes = [
            _node("tool_call", {"tool_name": "search_web"}),
            _node("investigate", {"tools": ["read_file"]}),
            _node("http_request", {}),
            _node("send_message", {}),
        ]
        assert derive_allowed_set(nodes) == {
            "search_web",
            "read_file",
            "node:http_request",
            "node:send_message",
        }


class TestDeriveAllowedSetFromJson:
    def test_round_trip_of_stored_shape(self) -> None:
        stored = json.dumps(
            [
                {"id": "n1", "type": "tool_call", "config": {"tool_name": "terminal"}},
                {"id": "n2", "type": "send_message", "config": {}},
            ]
        )
        assert derive_allowed_set_from_json(stored) == {
            "terminal",
            "node:send_message",
        }

    def test_degenerate_inputs_fail_closed(self) -> None:
        assert derive_allowed_set_from_json(None) == set()
        assert derive_allowed_set_from_json("") == set()
        assert derive_allowed_set_from_json("not json") == set()
        assert derive_allowed_set_from_json('{"a": 1}') == set()
        assert derive_allowed_set_from_json("[]") == set()


def test_every_node_type_is_classified():
    """L245 review finding 3: the classification invariant must be enforced.

    derive_allowed_set and the executor's effect refusal both key off this
    classification. A future node type that lands in neither the gated set,
    the effect markers, nor this hand-written inert set fails here instead
    of silently bypassing authorization.
    """
    from hestia.workflows.nodes import NODE_TYPES
    from hestia.workflows.tool_selection import (
        _GATED_NODE_TYPES,
        NODE_EFFECT_MARKERS,
    )

    explicitly_inert = {"condition", "llm_decision"}
    assert set(NODE_TYPES) == set(_GATED_NODE_TYPES) | set(NODE_EFFECT_MARKERS) | explicitly_inert, (
        "Unclassified node type detected. Every node type must be either "
        "gated (tool selection feeds the allow-list), effect-marked "
        "(activation authorizes it), or explicitly listed as inert here."
    )
