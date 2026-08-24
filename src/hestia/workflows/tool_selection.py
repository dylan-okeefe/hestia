"""Single source of truth for which tools a workflow node will invoke.

SEC-001 follow-up (review defect 1): the capability gate and the node
executors MUST agree on this list. The first gating implementation
duplicated resolution logic in two places with different type handling,
so a dict-shaped ``tools`` value skipped gating entirely while still
executing its keys. Both sides now call :func:`resolve_invoked_tools`,
which fails closed on any shape it does not recognize.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hestia.workflows.models import WorkflowNode

_GATED_NODE_TYPES = ("tool_call", "investigate")


def resolve_invoked_tools(node_type: str, node: WorkflowNode, inputs: dict[str, Any]) -> list[str]:
    """Return the tool names *node* will invoke, given resolved *inputs*.

    Raises:
        ValueError: On malformed configuration, or on any unrecognized
            value shape for ``tools``. Callers must treat that as a failed
            node — never as "no tools to gate".
    """
    if node_type == "tool_call":
        name = node.config.get("tool_name")
        if not isinstance(name, str) or not name:
            raise ValueError(
                "tool_call node requires a non-empty string 'tool_name' in config"
            )
        return [name]

    if node_type == "investigate":
        # L245: tools come from node.config ONLY. Trigger payloads must never
        # choose which tools an investigation runs - inputs are exactly the
        # attacker-influenceable channel that produced the round-1 bypass.
        raw = node.config.get("tools")
        if raw is None:
            return []
        if isinstance(raw, str):
            return [t.strip() for t in raw.split(",") if t.strip()]
        if isinstance(raw, list):
            if not all(isinstance(t, str) for t in raw):
                raise ValueError(
                    "investigate 'tools' list entries must all be strings"
                )
            return [t.strip() for t in raw if t.strip()]
        # Fail closed: a dict (or anything else) used to fall through the
        # gate with zero checks and then execute its keys directly.
        raise ValueError(
            "investigate 'tools' must be a string or a list of strings; "
            f"got {type(raw).__name__} — refusing to execute"
        )

    raise ValueError(
        f"resolve_invoked_tools called for ungated node type {node_type!r}"
    )


NODE_EFFECT_MARKERS: dict[str, str] = {
    "http_request": "node:http_request",
    "send_message": "node:send_message",
}
"""Markers representing node *effects* that are not registry tools.

Activating a workflow containing these nodes authorizes the effect, so the
derived allow-list records them explicitly. This makes the activation diff
honest ("this version adds direct HTTP calls") and lets the executor verify
the marker before running the node.
"""


def derive_allowed_set(nodes: list[WorkflowNode]) -> set[str]:
    """L245: derive the authorization set from a workflow's node graph.

    The result is exactly what activating this graph grants:
    - ``tool_call`` nodes contribute their configured tool name.
    - ``investigate`` nodes contribute their configured tools (malformed
      config contributes nothing — it fails closed at execution).
    - Effect nodes contribute their :data:`NODE_EFFECT_MARKERS` entry.

    Client-supplied allow-lists are never merged in; this function is the
    only source.
    """
    allowed: set[str] = set()
    for node in nodes:
        if node.type == "tool_call":
            name = node.config.get("tool_name")
            if isinstance(name, str) and name:
                allowed.add(name)
        elif node.type == "investigate":
            try:
                allowed.update(resolve_invoked_tools("investigate", node, {}))
            except ValueError:
                continue
        elif node.type in NODE_EFFECT_MARKERS:
            allowed.add(NODE_EFFECT_MARKERS[node.type])
    return allowed


def derive_allowed_set_from_json(nodes_json: str | None) -> set[str]:
    """Derive the authorization set from stored version JSON (m011 backfill).

    Accepts the exact shape ``WorkflowStore.save_version`` serializes. Any
    malformed input yields an empty set — a corrupt row must never widen
    an authorization.
    """
    import json

    if not nodes_json:
        return set()
    try:
        raw = json.loads(nodes_json)
    except (TypeError, ValueError):
        return set()
    if not isinstance(raw, list):
        return set()

    from hestia.workflows.models import WorkflowNode

    nodes: list[WorkflowNode] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        config = entry.get("config")
        nodes.append(
            WorkflowNode(
                id=str(entry.get("id", "")),
                type=str(entry.get("type", "")),
                label="",
                config=config if isinstance(config, dict) else {},
            )
        )
    return derive_allowed_set(nodes)
