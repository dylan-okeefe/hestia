"""Trigger registry: maps event-bus events to workflow executions."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from hestia.events.bus import EventBus
from hestia.workflows.models import Workflow
from hestia.workflows.store import WorkflowStore

logger = logging.getLogger(__name__)

WorkflowExecutor = Callable[[Workflow, Any], Awaitable[None]]

TRIGGER_MAP: dict[str, str] = {
    "schedule_fired": "schedule",
    "chat_command": "chat_command",
    "webhook_received": "webhook",
    "message_matched": "message",
}


class TriggerRegistry:
    """Wires workflow triggers to the event bus.

    On startup the registry loads all workflows from the store and
    subscribes a single handler per event type.  When an event fires,
    matching workflows are looked up and passed to the executor.
    """

    def __init__(
        self,
        event_bus: EventBus,
        workflow_store: WorkflowStore,
        executor: WorkflowExecutor,
    ) -> None:
        """Initialize the trigger registry.

        Args:
            event_bus: The event bus to subscribe to.
            workflow_store: Store for workflow definitions.
            executor: Async callable invoked with ``(workflow, payload)``.
        """
        self._event_bus = event_bus
        self._workflow_store = workflow_store
        self._executor = executor
        self._workflows: list[Workflow] = []
        self._started = False

    async def start(self) -> None:
        """Load workflows and subscribe handlers to the event bus.

        Idempotent: safe to call multiple times.
        """
        if self._started:
            return

        self._workflows = await self._workflow_store.list_workflows()

        for event_type in TRIGGER_MAP:
            self._event_bus.subscribe(event_type, self._on_event)

        self._started = True
        logger.info(
            "TriggerRegistry started: %d workflows, %d event types",
            len(self._workflows),
            len(TRIGGER_MAP),
        )

    async def reload(self) -> None:
        """Re-query all workflows from the store and replace the local cache."""
        self._workflows = await self._workflow_store.list_workflows()
        logger.info("TriggerRegistry reloaded: %d workflows", len(self._workflows))

    async def reload_one(self, workflow_id: str) -> None:
        """Fetch a single workflow and update or remove it from the local cache.

        Args:
            workflow_id: The ID of the workflow to refresh.
        """
        updated = await self._workflow_store.get_workflow(workflow_id)
        existing_ids = {w.id for w in self._workflows}

        if updated is not None:
            if workflow_id in existing_ids:
                self._workflows = [
                    updated if w.id == workflow_id else w for w in self._workflows
                ]
            else:
                self._workflows.append(updated)
            logger.debug("TriggerRegistry updated workflow %s", workflow_id)
        else:
            if workflow_id in existing_ids:
                self._workflows = [w for w in self._workflows if w.id != workflow_id]
                logger.debug("TriggerRegistry removed workflow %s", workflow_id)

    async def _on_event(self, event_type: str, payload: Any) -> None:
        """Handle an incoming event by matching and executing workflows."""
        trigger_type = TRIGGER_MAP.get(event_type)
        if trigger_type is None:
            logger.warning("Unknown event type %r", event_type)
            return

        matched = self._match_workflows(trigger_type, payload)
        for workflow in matched:
            try:
                await self._executor(workflow, payload)
            except Exception:
                logger.exception(
                    "Executor failed for workflow %s on event %r",
                    workflow.id,
                    event_type,
                )

    def _match_workflows(self, trigger_type: str, payload: Any) -> list[Workflow]:
        """Return workflows whose trigger matches the event."""
        matched: list[Workflow] = []
        for workflow in self._workflows:
            if workflow.trigger_type != trigger_type:
                continue

            if trigger_type == "schedule" and not self._schedule_matches(
                workflow, payload
            ):
                continue
            if trigger_type == "chat_command" and not self._command_matches(
                workflow, payload
            ):
                continue
            if trigger_type == "webhook" and not self._webhook_matches(
                workflow, payload
            ):
                continue
            if trigger_type == "message" and not self._message_matches(
                workflow, payload
            ):
                continue

            matched.append(workflow)
        return matched

    def _command_matches(self, workflow: Workflow, payload: Any) -> bool:
        """Check if a chat_command payload matches the workflow trigger config."""
        command = workflow.trigger_config.get("command")
        if command is None:
            return True
        if not isinstance(payload, dict):
            return False
        payload_command = payload.get("command")
        return bool(payload_command == command)

    def _webhook_matches(self, workflow: Workflow, payload: Any) -> bool:
        """Check if a webhook payload matches the workflow trigger config."""
        endpoint = workflow.trigger_config.get("endpoint")
        if endpoint is None:
            return True
        if not isinstance(payload, dict):
            return False
        payload_endpoint = payload.get("endpoint")
        return bool(payload_endpoint == endpoint)

    def _schedule_matches(self, workflow: Workflow, payload: Any) -> bool:
        """Check if a schedule payload matches the workflow trigger config."""
        cron = workflow.trigger_config.get("cron")
        if cron is None:
            return True
        if not isinstance(payload, dict):
            return False
        from datetime import datetime

        from croniter import croniter

        from hestia.core.clock import utcnow

        current_time = payload.get("current_time")
        if isinstance(current_time, str):
            current_time = datetime.fromisoformat(current_time)
        if current_time is None:
            current_time = utcnow()
        return bool(croniter.match(str(cron), current_time))

    def _message_matches(self, workflow: Workflow, payload: Any) -> bool:
        """Check if a message payload matches the workflow trigger config."""
        pattern = workflow.trigger_config.get("pattern")
        if pattern is None:
            return True
        if not isinstance(payload, dict):
            return False
        payload_text = payload.get("text")
        if not isinstance(payload_text, str):
            return False
        return bool(pattern in payload_text)
