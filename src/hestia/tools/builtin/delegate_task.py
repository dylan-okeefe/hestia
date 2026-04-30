"""Subagent delegation tool for spawning work in new sessions."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from hestia.core.clock import utcnow
from hestia.core.types import Message
from hestia.persistence.sessions import SessionStore

if TYPE_CHECKING:
    from hestia.orchestrator.types import Turn
from hestia.policy.constants import PLATFORM_SUBAGENT
from hestia.tools.capabilities import ORCHESTRATION
from hestia.tools.metadata import tool


@dataclass
class SubagentResult:
    """Structured result from a subagent delegation.

    This envelope keeps parent context growth bounded (~300 tokens)
    regardless of subagent work volume.
    """

    status: str  # "complete", "partial", "failed", "timeout"
    summary: str  # Brief description of what the subagent did
    completeness: float  # 0.0-1.0 estimate of task completion
    artifact_refs: list[str]  # Handles to stored artifacts (transcripts, etc.)
    error: str | None = None  # Error message if failed
    duration_seconds: float | None = None  # How long the subagent ran
    tool_calls_made: int = 0  # Count of tool calls in subagent
    follow_up_questions: list[str] | None = None  # Questions for the user
    next_actions: list[str] | None = None  # Suggested next steps

    def to_text(self) -> str:
        """Convert result to a text representation for the model."""
        lines = [
            f"Subagent result: {self.status}",
            f"Summary: {self.summary}",
            f"Completeness: {int(self.completeness * 100)}%",
        ]

        if self.error:
            lines.append(f"Error: {self.error}")

        if self.duration_seconds is not None:
            lines.append(f"Duration: {self.duration_seconds:.1f}s")

        if self.tool_calls_made > 0:
            lines.append(f"Tool calls: {self.tool_calls_made}")

        if self.artifact_refs:
            lines.append(f"Artifacts: {', '.join(self.artifact_refs)}")

        if self.follow_up_questions:
            lines.append("Follow-up questions:")
            for q in self.follow_up_questions:
                lines.append(f"  - {q}")

        if self.next_actions:
            lines.append("Suggested next actions:")
            for a in self.next_actions:
                lines.append(f"  - {a}")

        return "\n".join(lines)


def make_delegate_task_tool(
    session_store: SessionStore,
    orchestrator_factory: Callable[[], Any],  # Factory to create orchestrator for subagent
    default_timeout: float = 300.0,  # 5 minutes default
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Create a delegate_task tool bound to stores and orchestrator.

    Args:
        session_store: For creating subagent sessions
        orchestrator_factory: Factory that returns an orchestrator instance
        default_timeout: Default timeout in seconds

    Returns:
        The delegate_task tool function
    """

    @tool(
        name="delegate_task",
        public_description="Spawn a subagent to handle a task in a separate session with its own slot.",
        tags=["orchestration", "builtin"],
        capabilities=[ORCHESTRATION],
        parameters_schema={
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Description of the task to delegate",
                },
                "context": {
                    "type": "string",
                    "description": "Relevant context to pass to the subagent",
                },
                "timeout_seconds": {
                    "type": "number",
                    "description": f"Max seconds to run (default {default_timeout})",
                },
            },
            "required": ["task"],
        },
    )
    async def delegate_task(
        task: str,
        context: str = "",
        timeout_seconds: float | None = None,
    ) -> str:
        """Delegate a task to a subagent running in a separate session.

        The subagent gets its own slot and runs independently. Results are
        summarized to keep parent context bounded.

        Args:
            task: Description of what the subagent should do
            context: Additional context to provide to the subagent
            timeout_seconds: Timeout in seconds (uses default if not specified)

        Returns:
            SubagentResult as a formatted string
        """
        timeout = timeout_seconds or default_timeout

        # Create a new session for the subagent
        subagent_session = await session_store.create_session(
            platform=PLATFORM_SUBAGENT,
            platform_user=f"subagent_{uuid.uuid4().hex[:8]}",
        )

        start_time = utcnow()

        try:
            # Build the prompt for the subagent
            prompt_parts = [f"Task: {task}"]
            if context:
                prompt_parts.append(f"\nContext: {context}")
            prompt_parts.append(
                "\nWork on this task independently. When done, provide a concise summary "
                "of what you accomplished and any key findings."
            )
            prompt = "\n".join(prompt_parts)

            # Create user message for the subagent
            user_message = Message(role="user", content=prompt, created_at=utcnow())

            # Get orchestrator via factory. Each delegation gets a fresh
            # orchestrator (and typically its own SlotManager) for isolation;
            # VRAM is not shared with the parent turn.
            orchestrator = orchestrator_factory()

            # Run the subagent with timeout (respond_callback must be async — engine awaits it)
            async def _noop_respond(_: str) -> None:
                return None

            async def run_subagent() -> Turn:
                turn = await orchestrator.process_turn(
                    session=subagent_session,
                    user_message=user_message,
                    respond_callback=_noop_respond,
                    system_prompt="You are a focused subagent working on a specific task.",
                )
                return cast("Turn", turn)

            try:
                turn = await asyncio.wait_for(run_subagent(), timeout=timeout)

                duration = (utcnow() - start_time).total_seconds()
                artifact_refs = list(turn.artifact_handles)

                # Pull artifact handles the subagent's tool calls produced
                # during this turn. The engine populates
                # ``turn.artifact_handles`` as each successful tool call
                # returns an artifact handle; delegate_task surfaces them
                # to the caller so the parent can attach / reference them.

                # Determine status from turn (use string comparison to avoid circular import)
                state_value = getattr(turn.state, "value", str(turn.state))
                if state_value == "done":
                    status = "complete"
                    summary = turn.final_response or "Task completed"
                    completeness = 1.0
                elif state_value == "failed":
                    status = "failed"
                    summary = f"Subagent failed: {turn.error or 'Unknown error'}"
                    completeness = 0.0
                else:
                    status = "partial"
                    summary = f"Subagent ended in state: {state_value}"
                    completeness = 0.5

                result = SubagentResult(
                    status=status,
                    summary=summary,
                    completeness=completeness,
                    artifact_refs=artifact_refs,
                    error=turn.error if state_value == "failed" else None,
                    duration_seconds=duration,
                    tool_calls_made=turn.tool_calls_made,
                )

            except asyncio.TimeoutError:
                duration = (utcnow() - start_time).total_seconds()
                # On timeout we don't have a completed Turn to inspect, so
                # artifact_refs stays empty. Any artifacts the subagent did
                # produce remain reachable from the subagent session's
                # trace record even after archive.
                result = SubagentResult(
                    status="timeout",
                    summary=f"Subagent timed out after {timeout}s",
                    completeness=0.0,
                    artifact_refs=[],
                    error=f"Timeout after {timeout}s",
                    duration_seconds=duration,
                    tool_calls_made=0,  # We don't know
                )

            return result.to_text()

        finally:
            # Archive the subagent session
            await session_store.archive_session(subagent_session.id)

    return delegate_task
