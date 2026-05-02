"""Investigate node: uses LLM and optional tools to research a topic."""

from __future__ import annotations

import json
import logging
from typing import Any

from hestia.app import AppContext
from hestia.core.types import Message
from hestia.workflows.models import WorkflowNode

logger = logging.getLogger(__name__)

_MAX_DEEP_ITERATIONS = 3


class InvestigateNode:
    """Investigates a topic using LLM reasoning and optional tool calls."""

    async def execute(
        self,
        app: AppContext,
        node: WorkflowNode,
        inputs: dict[str, Any],
    ) -> Any:
        """Investigate the configured topic.

        Args:
            app: Application context.
            node: The workflow node.
            inputs: Resolved inputs for this node.

        Returns:
            Dict with ``topic``, ``findings``, ``recommendations``, and ``sources``.

        Raises:
            ValueError: If ``topic`` is not specified.
        """
        topic = _resolve("topic", node, inputs)
        depth = _resolve("depth", node, inputs) or "shallow"
        tools = _resolve("tools", node, inputs) or []

        if not topic:
            raise ValueError("InvestigateNode requires 'topic' in config or inputs")

        if isinstance(tools, str):
            tools = [t.strip() for t in tools.split(",") if t.strip()]

        tool_results: list[dict[str, Any]] = []
        for tool_name in tools:
            try:
                result = await app.tool_registry.call(tool_name, inputs)
                tool_results.append(
                    {
                        "tool": tool_name,
                        "status": result.status,
                        "content": result.content,
                    }
                )
            except Exception as exc:
                logger.warning("Tool %s failed for investigate node: %s", tool_name, exc)
                tool_results.append(
                    {
                        "tool": tool_name,
                        "status": "error",
                        "content": str(exc),
                    }
                )

        if depth == "deep":
            report = await self._deep_investigate(app, topic, tool_results)
        else:
            report = await self._shallow_investigate(app, topic, tool_results)

        return report

    async def _shallow_investigate(
        self,
        app: AppContext,
        topic: str,
        tool_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Single-pass investigation."""
        prompt = _build_prompt(topic, tool_results, iteration=1, max_iterations=1)
        response = await app.inference.chat(
            messages=[Message(role="user", content=prompt)],
            tools=None,
        )
        return _parse_report(topic, response.content)

    async def _deep_investigate(
        self,
        app: AppContext,
        topic: str,
        tool_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Multi-pass investigation with up to ``_MAX_DEEP_ITERATIONS`` calls."""
        findings: list[str] = []
        recommendations: list[str] = []
        sources: list[str] = []

        context = ""
        for iteration in range(1, _MAX_DEEP_ITERATIONS + 1):
            prompt = _build_prompt(
                topic,
                tool_results,
                iteration=iteration,
                max_iterations=_MAX_DEEP_ITERATIONS,
                prior_context=context,
            )
            response = await app.inference.chat(
                messages=[Message(role="user", content=prompt)],
                tools=None,
            )
            report = _parse_report(topic, response.content)

            findings.extend(report.get("findings", []))
            recommendations.extend(report.get("recommendations", []))
            sources.extend(report.get("sources", []))

            new_context = (
                f"Iteration {iteration} findings:\n"
                + "\n".join(f"- {f}" for f in report.get("findings", []))
            )
            context = f"{context}\n\n{new_context}".strip()

            if iteration == _MAX_DEEP_ITERATIONS:
                break

        return {
            "topic": topic,
            "findings": _dedupe(findings),
            "recommendations": _dedupe(recommendations),
            "sources": _dedupe(sources),
        }


def _resolve(key: str, node: WorkflowNode, inputs: dict[str, Any]) -> Any:
    """Resolve a value from ``inputs`` or ``node.config``."""
    return inputs.get(key, node.config.get(key))


def _build_prompt(
    topic: str,
    tool_results: list[dict[str, Any]],
    iteration: int,
    max_iterations: int,
    prior_context: str = "",
) -> str:
    """Construct the investigation prompt for the LLM."""
    lines: list[str] = [
        f"You are an investigative researcher. Investigate the following topic thoroughly.",
        f"",
        f"Topic: {topic}",
        f"",
    ]

    if tool_results:
        lines.append("Tool results:")
        for tr in tool_results:
            lines.append(f"- {tr['tool']}: {tr['content']}")
        lines.append("")

    if prior_context:
        lines.append("Prior findings from previous iterations:")
        lines.append(prior_context)
        lines.append("")

    if max_iterations > 1:
        lines.append(
            f"This is iteration {iteration} of {max_iterations}. "
            f"Deepen the investigation with new angles, facts, or sources."
        )
        lines.append("")

    lines.append(
        "Respond with a JSON object containing exactly these keys: "
        '"findings" (list of strings), "recommendations" (list of strings), "sources" (list of strings). '
        "Do not include markdown formatting or explanation outside the JSON."
    )

    return "\n".join(lines)


def _parse_report(topic: str, content: str) -> dict[str, Any]:
    """Parse the LLM response into a structured report."""
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```")
        cleaned = cleaned.removesuffix("```").strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Failed to parse investigation JSON, returning raw content as single finding")
        return {
            "topic": topic,
            "findings": [cleaned],
            "recommendations": [],
            "sources": [],
        }

    return {
        "topic": topic,
        "findings": _to_list(data.get("findings")),
        "recommendations": _to_list(data.get("recommendations")),
        "sources": _to_list(data.get("sources")),
    }


def _to_list(value: Any) -> list[str]:
    """Coerce a value to a list of strings."""
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    if value is None:
        return []
    return [str(value)]


def _dedupe(items: list[str]) -> list[str]:
    """Remove duplicate items while preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
