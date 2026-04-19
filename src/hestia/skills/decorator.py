"""Decorator for defining skills."""

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from hestia.errors import ExperimentalFeatureError
from hestia.skills.state import SkillState

EXPERIMENTAL_MESSAGE = (
    "Skills are an experimental preview. Set `HESTIA_EXPERIMENTAL_SKILLS=1` to opt in. "
    "See README.md#skills."
)


def _experimental_enabled() -> bool:
    return os.environ.get("HESTIA_EXPERIMENTAL_SKILLS") == "1"


@dataclass(frozen=True)
class SkillDefinition:
    """Metadata for a skill defined with @skill decorator."""

    name: str
    description: str
    required_tools: list[str]
    capabilities: list[str]
    state: SkillState
    handler: Callable[..., Any]
    file_path: str | None = None


def skill(
    *,
    name: str,
    description: str,
    required_tools: list[str] | None = None,
    capabilities: list[str] | None = None,
    state: SkillState = SkillState.DRAFT,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to define a skill.

    Skills are user-defined multi-step workflows that can be invoked
    by the model via the run_skill meta-tool.

    Args:
        name: Unique skill name (used for invocation)
        description: One-line description of what the skill does
        required_tools: List of tool names this skill requires
        capabilities: List of capabilities this skill needs
        state: Lifecycle state (default: draft)

    Example:
        @skill(
            name="daily_briefing",
            description="Fetch weather, calendar, and news, then summarize.",
            required_tools=["http_get", "search_memory"],
            capabilities=["network_egress", "memory_read"],
            state=SkillState.DRAFT,
        )
        async def daily_briefing(context: SkillContext) -> SkillResult:
            weather = await context.call_tool("http_get", url="https://wttr.in/?format=3")
            memories = await context.call_tool("search_memory", query="morning routine")
            return SkillResult(
                summary=f"Weather: {weather}\nRelevant memories: {memories}",
                status="success",
            )
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if not _experimental_enabled():
            raise ExperimentalFeatureError(EXPERIMENTAL_MESSAGE)
        # Create skill definition
        definition = SkillDefinition(
            name=name,
            description=description,
            required_tools=required_tools or [],
            capabilities=capabilities or [],
            state=state,
            handler=func,
            file_path=getattr(func, "__module__", None),
        )
        # Attach to function
        func.__hestia_skill__ = definition  # type: ignore[attr-defined]
        return func

    return decorator
