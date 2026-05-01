"""LLM decision node: asks the model to select a branch."""

from __future__ import annotations

import json
import logging
from typing import Any

from hestia.app import AppContext
from hestia.core.types import Message
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

        branch = response.content.strip()
        if branches and branch not in branches:
            logger.warning(
                "LLM returned unrecognized branch %r for node %s; allowed: %s",
                branch,
                node.id,
                branches,
            )

        return branch
