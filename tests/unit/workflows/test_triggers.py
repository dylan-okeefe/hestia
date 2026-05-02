"""Unit tests for TriggerRegistry."""

from __future__ import annotations

import asyncio
from datetime import UTC
from typing import Any

import pytest
import pytest_asyncio

from hestia.events.bus import EventBus
from hestia.persistence.db import Database
from hestia.workflows.models import Workflow
from hestia.workflows.store import WorkflowStore
from hestia.workflows.triggers import TriggerRegistry


@pytest_asyncio.fixture
async def db() -> Database:
    """Create an in-memory database for testing."""
    database = Database(url="sqlite+aiosqlite:///:memory:")
    await database.connect()
    await database.create_tables()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def workflow_store(db: Database) -> WorkflowStore:
    """Create a WorkflowStore for testing."""
    store = WorkflowStore(db)
    await store.create_tables()
    return store


@pytest.fixture
def event_bus() -> EventBus:
    """Return a fresh EventBus."""
    return EventBus()


@pytest.fixture
def executed() -> list[tuple[Workflow, Any]]:
    """Return a list to capture executor calls."""
    return []


@pytest_asyncio.fixture
async def registry(
    event_bus: EventBus,
    workflow_store: WorkflowStore,
    executed: list[tuple[Workflow, Any]],
) -> TriggerRegistry:
    """Create a TriggerRegistry for testing."""

    async def executor(workflow: Workflow, payload: Any) -> None:
        executed.append((workflow, payload))

    reg = TriggerRegistry(event_bus, workflow_store, executor)
    await reg.start()
    return reg


class TestStart:
    """Tests for registry startup."""

    @pytest.mark.asyncio
    async def test_start_is_idempotent(
        self,
        event_bus: EventBus,
        workflow_store: WorkflowStore,
        executed: list[tuple[Workflow, Any]],
    ) -> None:
        """Calling start() multiple times is safe."""

        async def executor(workflow: Workflow, payload: Any) -> None:
            executed.append((workflow, payload))

        reg = TriggerRegistry(event_bus, workflow_store, executor)
        await reg.start()
        await reg.start()
        # No exception means success


class TestScheduleFired:
    """Tests for schedule_fired events."""

    @pytest.mark.asyncio
    async def test_schedule_trigger_matches(
        self,
        workflow_store: WorkflowStore,
        event_bus: EventBus,
        executed: list[tuple[Workflow, Any]],
    ) -> None:
        """A workflow with trigger_type 'schedule' runs on schedule_fired."""
        wf = Workflow(id="wf_1", name="Daily Report", trigger_type="schedule")
        await workflow_store.save_workflow(wf)

        async def executor(workflow: Workflow, payload: Any) -> None:
            executed.append((workflow, payload))

        reg = TriggerRegistry(event_bus, workflow_store, executor)
        await reg.start()

        await event_bus.publish("schedule_fired", {"task_id": "t1"})
        await asyncio.sleep(0.01)

        assert len(executed) == 1
        assert executed[0][0].id == "wf_1"

    @pytest.mark.asyncio
    async def test_non_schedule_trigger_ignored(
        self,
        workflow_store: WorkflowStore,
        event_bus: EventBus,
        executed: list[tuple[Workflow, Any]],
    ) -> None:
        """A workflow with trigger_type 'manual' does not run on schedule_fired."""
        wf = Workflow(id="wf_1", name="Manual", trigger_type="manual")
        await workflow_store.save_workflow(wf)

        async def executor(workflow: Workflow, payload: Any) -> None:
            executed.append((workflow, payload))

        reg = TriggerRegistry(event_bus, workflow_store, executor)
        await reg.start()

        await event_bus.publish("schedule_fired", {"task_id": "t1"})
        await asyncio.sleep(0.01)

        assert executed == []


class TestChatCommand:
    """Tests for chat_command events."""

    @pytest.mark.asyncio
    async def test_command_matches(
        self,
        workflow_store: WorkflowStore,
        event_bus: EventBus,
        executed: list[tuple[Workflow, Any]],
    ) -> None:
        """Workflow runs when the command matches."""
        wf = Workflow(
            id="wf_1",
            name="Status",
            trigger_type="chat_command",
            trigger_config={"command": "status"},
        )
        await workflow_store.save_workflow(wf)

        async def executor(workflow: Workflow, payload: Any) -> None:
            executed.append((workflow, payload))

        reg = TriggerRegistry(event_bus, workflow_store, executor)
        await reg.start()

        await event_bus.publish("chat_command", {"command": "status"})
        await asyncio.sleep(0.01)

        assert len(executed) == 1

    @pytest.mark.asyncio
    async def test_command_mismatch(
        self,
        workflow_store: WorkflowStore,
        event_bus: EventBus,
        executed: list[tuple[Workflow, Any]],
    ) -> None:
        """Workflow is skipped when the command does not match."""
        wf = Workflow(
            id="wf_1",
            name="Status",
            trigger_type="chat_command",
            trigger_config={"command": "status"},
        )
        await workflow_store.save_workflow(wf)

        async def executor(workflow: Workflow, payload: Any) -> None:
            executed.append((workflow, payload))

        reg = TriggerRegistry(event_bus, workflow_store, executor)
        await reg.start()

        await event_bus.publish("chat_command", {"command": "help"})
        await asyncio.sleep(0.01)

        assert executed == []

    @pytest.mark.asyncio
    async def test_no_command_config_matches_any(
        self,
        workflow_store: WorkflowStore,
        event_bus: EventBus,
        executed: list[tuple[Workflow, Any]],
    ) -> None:
        """Workflow with no command config matches any chat_command."""
        wf = Workflow(
            id="wf_1",
            name="Catch All",
            trigger_type="chat_command",
            trigger_config={},
        )
        await workflow_store.save_workflow(wf)

        async def executor(workflow: Workflow, payload: Any) -> None:
            executed.append((workflow, payload))

        reg = TriggerRegistry(event_bus, workflow_store, executor)
        await reg.start()

        await event_bus.publish("chat_command", {"command": "anything"})
        await asyncio.sleep(0.01)

        assert len(executed) == 1


class TestWebhookReceived:
    """Tests for webhook_received events."""

    @pytest.mark.asyncio
    async def test_endpoint_matches(
        self,
        workflow_store: WorkflowStore,
        event_bus: EventBus,
        executed: list[tuple[Workflow, Any]],
    ) -> None:
        """Workflow runs when the endpoint matches."""
        wf = Workflow(
            id="wf_1",
            name="Hook",
            trigger_type="webhook",
            trigger_config={"endpoint": "/deploy"},
        )
        await workflow_store.save_workflow(wf)

        async def executor(workflow: Workflow, payload: Any) -> None:
            executed.append((workflow, payload))

        reg = TriggerRegistry(event_bus, workflow_store, executor)
        await reg.start()

        await event_bus.publish("webhook_received", {"endpoint": "/deploy"})
        await asyncio.sleep(0.01)

        assert len(executed) == 1

    @pytest.mark.asyncio
    async def test_endpoint_mismatch(
        self,
        workflow_store: WorkflowStore,
        event_bus: EventBus,
        executed: list[tuple[Workflow, Any]],
    ) -> None:
        """Workflow is skipped when the endpoint does not match."""
        wf = Workflow(
            id="wf_1",
            name="Hook",
            trigger_type="webhook",
            trigger_config={"endpoint": "/deploy"},
        )
        await workflow_store.save_workflow(wf)

        async def executor(workflow: Workflow, payload: Any) -> None:
            executed.append((workflow, payload))

        reg = TriggerRegistry(event_bus, workflow_store, executor)
        await reg.start()

        await event_bus.publish("webhook_received", {"endpoint": "/other"})
        await asyncio.sleep(0.01)

        assert executed == []


class TestMessageMatched:
    """Tests for message_matched events."""

    @pytest.mark.asyncio
    async def test_pattern_matches(
        self,
        workflow_store: WorkflowStore,
        event_bus: EventBus,
        executed: list[tuple[Workflow, Any]],
    ) -> None:
        """Workflow runs when the message text contains the pattern."""
        wf = Workflow(
            id="wf_1",
            name="Alert",
            trigger_type="message",
            trigger_config={"pattern": "ERROR"},
        )
        await workflow_store.save_workflow(wf)

        async def executor(workflow: Workflow, payload: Any) -> None:
            executed.append((workflow, payload))

        reg = TriggerRegistry(event_bus, workflow_store, executor)
        await reg.start()

        await event_bus.publish("message_matched", {"text": "System ERROR detected"})
        await asyncio.sleep(0.01)

        assert len(executed) == 1

    @pytest.mark.asyncio
    async def test_pattern_mismatch(
        self,
        workflow_store: WorkflowStore,
        event_bus: EventBus,
        executed: list[tuple[Workflow, Any]],
    ) -> None:
        """Workflow is skipped when the message text does not contain the pattern."""
        wf = Workflow(
            id="wf_1",
            name="Alert",
            trigger_type="message",
            trigger_config={"pattern": "ERROR"},
        )
        await workflow_store.save_workflow(wf)

        async def executor(workflow: Workflow, payload: Any) -> None:
            executed.append((workflow, payload))

        reg = TriggerRegistry(event_bus, workflow_store, executor)
        await reg.start()

        await event_bus.publish("message_matched", {"text": "All clear"})
        await asyncio.sleep(0.01)

        assert executed == []


class TestScheduleMatching:
    """Tests for schedule trigger cron matching."""

    @pytest.mark.asyncio
    async def test_schedule_no_cron_matches_any(
        self,
        workflow_store: WorkflowStore,
        event_bus: EventBus,
        executed: list[tuple[Workflow, Any]],
    ) -> None:
        """A schedule workflow without a cron expression matches any schedule event."""
        wf = Workflow(id="wf_1", name="Any Time", trigger_type="schedule")
        await workflow_store.save_workflow(wf)

        async def executor(workflow: Workflow, payload: Any) -> None:
            executed.append((workflow, payload))

        reg = TriggerRegistry(event_bus, workflow_store, executor)
        await reg.start()

        await event_bus.publish("schedule_fired", {"task_id": "t1"})
        await asyncio.sleep(0.01)

        assert len(executed) == 1

    @pytest.mark.asyncio
    async def test_schedule_cron_matches(
        self,
        workflow_store: WorkflowStore,
        event_bus: EventBus,
        executed: list[tuple[Workflow, Any]],
    ) -> None:
        """A schedule workflow with a matching cron expression runs."""
        wf = Workflow(
            id="wf_1",
            name="Hourly",
            trigger_type="schedule",
            trigger_config={"cron": "0 * * * *"},
        )
        await workflow_store.save_workflow(wf)

        async def executor(workflow: Workflow, payload: Any) -> None:
            executed.append((workflow, payload))

        reg = TriggerRegistry(event_bus, workflow_store, executor)
        await reg.start()

        from datetime import datetime

        await event_bus.publish(
            "schedule_fired",
            {"task_id": "t1", "current_time": datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)},
        )
        await asyncio.sleep(0.01)

        assert len(executed) == 1

    @pytest.mark.asyncio
    async def test_schedule_cron_mismatch(
        self,
        workflow_store: WorkflowStore,
        event_bus: EventBus,
        executed: list[tuple[Workflow, Any]],
    ) -> None:
        """A schedule workflow with a non-matching cron expression is skipped."""
        wf = Workflow(
            id="wf_1",
            name="Midnight Only",
            trigger_type="schedule",
            trigger_config={"cron": "0 0 * * *"},
        )
        await workflow_store.save_workflow(wf)

        async def executor(workflow: Workflow, payload: Any) -> None:
            executed.append((workflow, payload))

        reg = TriggerRegistry(event_bus, workflow_store, executor)
        await reg.start()

        from datetime import datetime

        await event_bus.publish(
            "schedule_fired",
            {"task_id": "t1", "current_time": datetime(2024, 1, 1, 12, 30, 0, tzinfo=UTC)},
        )
        await asyncio.sleep(0.01)

        assert executed == []


class TestMultipleWorkflows:
    """Tests for multiple workflows matching."""

    @pytest.mark.asyncio
    async def test_multiple_matching_workflows(
        self,
        workflow_store: WorkflowStore,
        event_bus: EventBus,
        executed: list[tuple[Workflow, Any]],
    ) -> None:
        """All matching workflows are executed."""
        wf1 = Workflow(id="wf_1", name="A", trigger_type="schedule")
        wf2 = Workflow(id="wf_2", name="B", trigger_type="schedule")
        await workflow_store.save_workflow(wf1)
        await workflow_store.save_workflow(wf2)

        async def executor(workflow: Workflow, payload: Any) -> None:
            executed.append((workflow, payload))

        reg = TriggerRegistry(event_bus, workflow_store, executor)
        await reg.start()

        await event_bus.publish("schedule_fired", {"task_id": "t1"})
        await asyncio.sleep(0.01)

        assert len(executed) == 2
        ids = {w.id for w, _p in executed}
        assert ids == {"wf_1", "wf_2"}


class TestReload:
    """Tests for reload and reload_one methods."""

    @pytest.mark.asyncio
    async def test_reload_updates_workflows(
        self,
        workflow_store: WorkflowStore,
        event_bus: EventBus,
        executed: list[tuple[Workflow, Any]],
    ) -> None:
        """reload refreshes the workflow list from the store."""
        wf1 = Workflow(id="wf_1", name="A", trigger_type="schedule")
        await workflow_store.save_workflow(wf1)

        async def executor(workflow: Workflow, payload: Any) -> None:
            executed.append((workflow, payload))

        reg = TriggerRegistry(event_bus, workflow_store, executor)
        await reg.start()

        # Add a new workflow after start
        wf2 = Workflow(id="wf_2", name="B", trigger_type="schedule")
        await workflow_store.save_workflow(wf2)

        # Before reload, only wf1 is known
        await event_bus.publish("schedule_fired", {"task_id": "t1"})
        await asyncio.sleep(0.01)
        assert len(executed) == 1

        # After reload, wf2 is also known
        await reg.reload()
        await event_bus.publish("schedule_fired", {"task_id": "t2"})
        await asyncio.sleep(0.01)
        assert len(executed) == 3
        ids = {w.id for w, _p in executed}
        assert ids == {"wf_1", "wf_2"}

    @pytest.mark.asyncio
    async def test_reload_one_updates_single_workflow(
        self,
        workflow_store: WorkflowStore,
        event_bus: EventBus,
        executed: list[tuple[Workflow, Any]],
    ) -> None:
        """reload_one updates a single workflow without full reload."""
        wf = Workflow(id="wf_1", name="Old", trigger_type="schedule")
        await workflow_store.save_workflow(wf)

        async def executor(workflow: Workflow, payload: Any) -> None:
            executed.append((workflow, payload))

        reg = TriggerRegistry(event_bus, workflow_store, executor)
        await reg.start()

        # Update the workflow in the store
        wf.name = "New"
        await workflow_store.save_workflow(wf)

        await reg.reload_one("wf_1")

        assert len(reg._workflows) == 1
        assert reg._workflows[0].name == "New"

    @pytest.mark.asyncio
    async def test_reload_one_adds_new_workflow(
        self,
        workflow_store: WorkflowStore,
        event_bus: EventBus,
        executed: list[tuple[Workflow, Any]],
    ) -> None:
        """reload_one adds a workflow that was not previously cached."""
        async def executor(workflow: Workflow, payload: Any) -> None:
            executed.append((workflow, payload))

        reg = TriggerRegistry(event_bus, workflow_store, executor)
        await reg.start()

        wf = Workflow(id="wf_1", name="A", trigger_type="schedule")
        await workflow_store.save_workflow(wf)

        await reg.reload_one("wf_1")

        assert len(reg._workflows) == 1
        assert reg._workflows[0].id == "wf_1"

    @pytest.mark.asyncio
    async def test_reload_one_removes_deleted_workflow(
        self,
        workflow_store: WorkflowStore,
        event_bus: EventBus,
        executed: list[tuple[Workflow, Any]],
    ) -> None:
        """reload_one removes a workflow that no longer exists in the store."""
        wf = Workflow(id="wf_1", name="A", trigger_type="schedule")
        await workflow_store.save_workflow(wf)

        async def executor(workflow: Workflow, payload: Any) -> None:
            executed.append((workflow, payload))

        reg = TriggerRegistry(event_bus, workflow_store, executor)
        await reg.start()

        await workflow_store.delete_workflow("wf_1")
        await reg.reload_one("wf_1")

        assert reg._workflows == []
