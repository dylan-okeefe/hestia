"""Rollback tool — restore files to a previous checkpoint."""

from typing import Any

from hestia.runtime_context import current_turn_id
from hestia.tools.capabilities import SELF_MANAGEMENT
from hestia.tools.checkpoint import CheckpointManager
from hestia.tools.metadata import tool


def make_rollback_turn_tool(checkpoint_manager: CheckpointManager) -> Any:
    """Create a rollback_turn tool bound to a CheckpointManager."""

    @tool(
        name="rollback_turn",
        public_description=(
            "Restore files to the checkpoint taken at the start of a turn. "
            "If no turn_id is given, rolls back the current turn."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "turn_id": {
                    "type": "string",
                    "description": "Turn ID to roll back. Omit to roll back the current turn.",
                },
            },
        },
        requires_confirmation=True,
        tags=["system", "builtin"],
        capabilities=[SELF_MANAGEMENT],
    )
    async def rollback_turn(turn_id: str = "") -> str:
        """Restore files to the checkpoint taken at the start of *turn_id*
        (or the current turn if *turn_id* is empty).
        """
        target = turn_id.strip() or current_turn_id.get(None)
        if not target:
            return (
                "Error: no turn_id provided and no current turn is active. "
                "Specify a turn_id explicitly."
            )

        try:
            checkpoint_manager.restore(target)
        except ValueError as exc:
            return f"Error: {exc}"
        except Exception as exc:  # noqa: BLE001
            return f"Error restoring checkpoint: {exc}"

        return f"Rolled back files to checkpoint for turn {target}."

    return rollback_turn
