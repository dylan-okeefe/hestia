"""Workflow data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class WorkflowNode:
    """A node in a workflow graph."""

    id: str
    type: str
    label: str
    config: dict[str, Any] = field(default_factory=dict)
    position: dict[str, float] = field(default_factory=dict)


@dataclass
class WorkflowEdge:
    """An edge connecting two nodes in a workflow graph."""

    id: str
    source_node_id: str
    target_node_id: str
    source_handle: str | None = None
    target_handle: str | None = None
    condition: str | None = None


@dataclass
class WorkflowVersion:
    """A versioned snapshot of a workflow's graph."""

    workflow_id: str
    version: int
    nodes: list[WorkflowNode] = field(default_factory=list)
    edges: list[WorkflowEdge] = field(default_factory=list)
    created_at: datetime | None = None
    is_active: bool = False


@dataclass
class Workflow:
    """A workflow definition."""

    id: str
    name: str
    description: str = ""
    trigger_type: str = "manual"
    trigger_config: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
