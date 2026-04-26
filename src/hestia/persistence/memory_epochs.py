"""Memory epoch compilation helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hestia.core.types import Session

if TYPE_CHECKING:
    from hestia.app import CliAppContext


async def _compile_and_set_memory_epoch(
    app: CliAppContext,
    session: Session,
) -> bool:
    """Compile memory epoch for the session and set it in context builder.

    Args:
        app: The CLI app context
        session: The current session

    Returns:
        True if an epoch was compiled and set, False otherwise
    """
    if app.epoch_compiler is None:
        return False

    epoch = await app.epoch_compiler.compile(session)
    if epoch.memory_count > 0:
        app.context_builder.set_memory_epoch_prefix(epoch.compiled_text)
        return True
    return False
