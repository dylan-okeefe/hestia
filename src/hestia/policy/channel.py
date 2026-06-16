"""Execution channels for capability gating."""

from __future__ import annotations

from enum import StrEnum


class Channel(StrEnum):
    """Channel over which a tool execution request originates."""

    CLI = "cli"
    TELEGRAM = "telegram"
    MATRIX = "matrix"
    EMAIL = "email"
    WEBHOOK = "webhook"
    SCHEDULER = "scheduler"
    WORKFLOW = "workflow"
    SUBAGENT = "subagent"
    API = "api"
