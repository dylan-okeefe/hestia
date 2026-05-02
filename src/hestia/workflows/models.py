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
    capabilities: list[str] = field(default_factory=list)


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
    owner_id: str = ""
    trust_level: str = "paranoid"
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class NodeResult:
    """Result of executing a single workflow node."""

    node_id: str
    status: str  # "ok" | "failed"
    output: Any = None
    error: str | None = None
    elapsed_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class ExecutionResult:
    """Result of executing a workflow."""

    workflow_id: str
    status: str  # "ok" | "failed"
    node_results: list[NodeResult] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)
    total_elapsed_ms: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
