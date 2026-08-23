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
        # Inputs take precedence over config, mirroring InvestigateNode's
        # historical _resolve precedence.
        raw = inputs.get("tools", node.config.get("tools"))
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
