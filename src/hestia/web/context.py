"""WebContext dataclass and dependency injection for dashboard routes."""

from __future__ import annotations

from dataclasses import dataclass, field

from hestia.app import AppContext
from hestia.orchestrator.handoff_service import HandoffService
from hestia.persistence.error_resolution_store import ErrorResolutionStore
from hestia.persistence.failure_store import FailureStore
from hestia.persistence.message_store import MessageStore
from hestia.persistence.scheduler import SchedulerStore
from hestia.persistence.session_store import SessionStore
from hestia.persistence.trace_store import TraceStore
from hestia.persistence.turn_store import TurnStore
from hestia.persistence.users import UserStore
from hestia.reflection.store import ProposalStore
from hestia.style.store import StyleProfileStore
from hestia.tools.browser.session_store import BrowserSessionStore
from hestia.web.auth import AuthManager
from hestia.web.browser_stream import SessionStreamManager
from hestia.workflows.execution_store import ExecutionStore
from hestia.workflows.store import WorkflowStore
from hestia.workflows.triggers import TriggerRegistry


@dataclass
class WebContext:
    """Holds references to stores and app context for web routes."""

    session_store: SessionStore
    proposal_store: ProposalStore
    style_store: StyleProfileStore
    scheduler_store: SchedulerStore
    trace_store: TraceStore
    failure_store: FailureStore
    workflow_store: WorkflowStore
    execution_store: ExecutionStore
    app: AppContext
    user_store: UserStore
    message_store: MessageStore | None = field(default=None)
    turn_store: TurnStore | None = field(default=None)
    handoff_service: HandoffService | None = field(default=None)
    error_resolution_store: ErrorResolutionStore | None = field(default=None)
    auth_manager: AuthManager | None = field(default=None)
    trigger_registry: TriggerRegistry | None = field(default=None)
    browser_session_store: BrowserSessionStore | None = field(default=None)
    stream_manager: SessionStreamManager | None = field(default=None)

    def __post_init__(self) -> None:
        """Derive split stores from the session store when not provided."""
        if self.message_store is None:
            self.message_store = MessageStore(self.session_store._db)
        if self.turn_store is None:
            self.turn_store = TurnStore(self.session_store._db)
        if self.handoff_service is None:
            self.handoff_service = HandoffService(
                self.session_store, self.message_store
            )


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
