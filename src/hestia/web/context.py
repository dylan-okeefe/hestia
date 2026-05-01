"""WebContext dataclass and dependency injection for dashboard routes."""

from __future__ import annotations

from dataclasses import dataclass, field

from hestia.app import AppContext
from hestia.persistence.failure_store import FailureStore
from hestia.persistence.scheduler import SchedulerStore
from hestia.persistence.sessions import SessionStore
from hestia.persistence.trace_store import TraceStore
from hestia.reflection.store import ProposalStore
from hestia.style.store import StyleProfileStore
from hestia.web.auth import AuthManager


@dataclass
class WebContext:
    """Holds references to stores and app context for web routes."""

    session_store: SessionStore
    proposal_store: ProposalStore
    style_store: StyleProfileStore
    scheduler_store: SchedulerStore
    trace_store: TraceStore
    failure_store: FailureStore
    app: AppContext
    auth_manager: AuthManager | None = field(default=None)


# Global singleton — adequate for single-worker uvicorn but will break
# with multiple workers. Use a shared external store if scaling beyond one process.
_ctx: WebContext | None = None


def set_web_context(ctx: WebContext) -> None:
    """Set the global web context (called once during server startup)."""
    global _ctx
    _ctx = ctx


def get_web_context() -> WebContext:
    """Return the current web context.

    Raises:
        RuntimeError: if the context has not been set.
    """
    if _ctx is None:
        raise RuntimeError("WebContext not set")
    return _ctx
