"""LLM decision node: asks the model to select a branch."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from hestia.app import AppContext
from hestia.core.types import ChatResponse, Message
from hestia.workflows.interpolation import interpolate
from hestia.workflows.models import WorkflowNode

logger = logging.getLogger(__name__)


class LLMDecisionNode:
    """Sends context to inference and expects structured branch selection."""

    async def execute(
        self,
        app: AppContext,
        node: WorkflowNode,
        inputs: dict[str, Any],
    ) -> Any:
        """Ask the LLM to select a branch based on the provided context.

        Args:
            app: Application context.
            node: The workflow node.
            inputs: Resolved inputs for this node.

        Returns:
            The selected branch name or identifier.
        """
        branches = node.config.get("branches", [])
        prompt_template = node.config.get(
            "prompt",
            "Based on the following context, select the most appropriate branch.",
        )

        if prompt_template and isinstance(prompt_template, str):
            prompt_template = interpolate(prompt_template, inputs)

        context = json.dumps(inputs, indent=2, default=str)
        branch_list = (
            "\n".join(f"- {b}" for b in branches)
            if branches
            else "(no branches configured)"
        )

        prompt = (
            f"{prompt_template}\n\n"
            f"Context:\n{context}\n\n"
            f"Available branches:\n{branch_list}\n\n"
            "Respond with only the branch name."
        )

        response = await app.inference.chat(
            messages=[Message(role="user", content=prompt)],
            tools=None,
        )

        branch = (response.content or "").strip()
        if not branch and response.reasoning_content:
            # Fallback for reasoning models that put the answer in
            # reasoning_content instead of content.
            lines = [
                line.strip()
                for line in response.reasoning_content.strip().split("\n")
                if line.strip()
            ]
            if lines:
                raw = lines[-1]
                # Strip markdown formatting
                raw = re.sub(r"^[\s*\-+•]+", "", raw)
                raw = raw.replace("`", "")
                raw = re.sub(r"\*\*?(.*?)\*\*?", r"\1", raw)
                raw = raw.strip('"\'')
                branch = raw.strip()
        if branches and branch not in branches:
            # Try to find an allowed branch anywhere in the reasoning
            if response.reasoning_content:
                for b in branches:
                    if re.search(rf"\b{re.escape(b)}\b", response.reasoning_content):
                        branch = b
                        break
            if branch not in branches:
                logger.warning(
                    "LLM returned unrecognized branch %r for node %s; allowed: %s",
                    branch,
                    node.id,
                    branches,
                )

        return ChatResponse(
            content=branch,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_tokens=response.total_tokens,
            finish_reason=response.finish_reason,
            reasoning_content=response.reasoning_content,
            tool_calls=response.tool_calls,
        )
