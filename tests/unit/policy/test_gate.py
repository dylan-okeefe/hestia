"""Unit tests for the CapabilityGate core."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest

from hestia.artifacts.store import ArtifactStore
from hestia.config import HestiaConfig, TrustConfig
from hestia.persistence.capability_events import CapabilityEventStore
from hestia.persistence.db import Database
from hestia.persistence.users import UserStore
from hestia.policy import CapabilityGate, CapabilityRequest, Channel, Identity
from hestia.tools.capabilities import EMAIL_SEND, READ_LOCAL, SHELL_EXEC, WRITE_LOCAL
from hestia.tools.metadata import tool
from hestia.tools.registry import ToolRegistry


@pytest.fixture
async def db() -> AsyncGenerator[Database, None]:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.connect()
    await database.create_tables()
    yield database
    await database.close()


@pytest.fixture
def registry(tmp_path: Any) -> ToolRegistry:
    artifact_store = ArtifactStore(tmp_path / "artifacts")
    reg = ToolRegistry(artifact_store)

    @tool(name="read_file", public_description="Read a file", capabilities=[READ_LOCAL])
    async def read_file(path: str) -> str:
        return ""

    @tool(
        name="terminal",
        public_description="Run a shell command",
        capabilities=[SHELL_EXEC],
        requires_confirmation=True,
    )
    async def terminal(command: str) -> str:
        return ""

    @tool(name="write_file", public_description="Write a file", capabilities=[WRITE_LOCAL])
    async def write_file(path: str, content: str) -> str:
        return ""

    @tool(name="email_send", public_description="Send email", capabilities=[EMAIL_SEND])
    async def email_send(to: str, subject: str, body: str) -> str:
        return ""

    reg.register(read_file)
    reg.register(terminal)
    reg.register(write_file)
    reg.register(email_send)
    return reg


def make_gate(config: HestiaConfig, db: Database, registry: ToolRegistry) -> CapabilityGate:
    return CapabilityGate(
        config=config,
        user_store=UserStore(db),
        registry=registry,
        event_store=CapabilityEventStore(db),
    )


async def make_user(
    db: Database,
    display_name: str,
    platform: str,
    platform_user: str,
    trust_preset: str | None = None,
) -> Identity:
    store = UserStore(db)
    user = await store.create_user(display_name, trust_preset=trust_preset)
    await store.add_identity(user.id, platform, platform_user, verified=True)
    return Identity(platform=platform, platform_user=platform_user, user_id=user.id)


class TestCapabilityGate:
    async def test_unknown_actor_on_untrusted_channel_is_restricted(
        self, db: Database, registry: ToolRegistry
    ) -> None:
        cfg = HestiaConfig.default()
        gate = make_gate(cfg, db, registry)
        request = CapabilityRequest(
            actor=Identity(platform="email", platform_user="stranger@example.com"),
            channel=Channel.EMAIL,
            tool_name="terminal",
            inputs={"command": "whoami"},
        )
        result = await gate.check(request)
        assert result.allowed is False
        assert result.reason == "unknown_actor_untrusted_channel"
        events = await CapabilityEventStore(db).list_recent()
        assert len(events) == 1
        assert events[0].decision == "denied"

    async def test_user_trust_preset_child_overrides_config_preset(
        self, db: Database, registry: ToolRegistry
    ) -> None:
        cfg = HestiaConfig.default()
        cfg.trust = TrustConfig.developer()
        gate = make_gate(cfg, db, registry)
        actor = await make_user(db, "Kid", "telegram", "kid123", trust_preset="child")
        request = CapabilityRequest(
            actor=actor,
            channel=Channel.CLI,
            tool_name="terminal",
            inputs={"command": "whoami"},
        )
        result = await gate.check(request)
        assert result.allowed is True
        assert result.auto_approved is False
        assert result.requires_confirmation is False

    async def test_trust_overrides_still_win(
        self, db: Database, registry: ToolRegistry
    ) -> None:
        cfg = HestiaConfig.default()
        cfg.trust = TrustConfig.paranoid()
        cfg.trust_overrides = {"telegram:overridden": TrustConfig.developer()}
        gate = make_gate(cfg, db, registry)
        actor = await make_user(db, "Overridden", "telegram", "overridden", trust_preset="child")
        request = CapabilityRequest(
            actor=actor,
            channel=Channel.CLI,
            tool_name="terminal",
            inputs={"command": "whoami"},
        )
        result = await gate.check(request)
        assert result.allowed is True
        assert result.auto_approved is True

    async def test_developer_preset_keeps_trusted_channels_auto_approve_for_safe_tools(
        self, db: Database, registry: ToolRegistry
    ) -> None:
        cfg = HestiaConfig.default()
        cfg.trust = TrustConfig.developer()
        gate = make_gate(cfg, db, registry)
        for channel in (Channel.CLI, Channel.TELEGRAM, Channel.MATRIX):
            request = CapabilityRequest(
                actor=Identity(platform=channel.value, platform_user="owner"),
                channel=channel,
                tool_name="read_file",
                inputs={"path": "notes.txt"},
            )
            result = await gate.check(request)
            assert result.allowed is True
            assert result.auto_approved is True
            assert result.requires_confirmation is False

    async def test_destructive_tool_in_workflow_is_denied_without_allow_list(
        self, db: Database, registry: ToolRegistry
    ) -> None:
        cfg = HestiaConfig.default()
        cfg.trust = TrustConfig.developer()
        gate = make_gate(cfg, db, registry)
        owner = await make_user(db, "Owner", "telegram", "wf-owner")
        request = CapabilityRequest(
            actor=owner,
            channel=Channel.WORKFLOW,
            tool_name="terminal",
            inputs={"command": "rm -rf /"},
            source_workflow_id="wf-1",
        )
        result = await gate.check(request)
        assert result.allowed is False
        assert result.reason == "not_allow_listed"
        events = await CapabilityEventStore(db).list_recent()
        assert len(events) == 1
        assert events[0].decision == "denied"
        assert events[0].source_workflow_id == "wf-1"

    async def test_destructive_tool_in_workflow_allow_listed(
        self, db: Database, registry: ToolRegistry
    ) -> None:
        cfg = HestiaConfig.default()
        cfg.trust = TrustConfig.developer()
        gate = make_gate(cfg, db, registry)
        request = CapabilityRequest(
            actor=Identity(platform="workflow", platform_user="wf-owner"),
            channel=Channel.WORKFLOW,
            tool_name="terminal",
            inputs={"command": "ls"},
            source_workflow_id="wf-1",
        )
        result = await gate.check(request, allow_list={"terminal"})
        assert result.allowed is True
        assert result.auto_approved is True
        assert result.requires_confirmation is False

    async def test_injection_escalation_denies_unattended(
        self, db: Database, registry: ToolRegistry
    ) -> None:
        cfg = HestiaConfig.default()
        cfg.trust = TrustConfig.developer()
        gate = make_gate(cfg, db, registry)
        owner = await make_user(db, "Owner", "telegram", "wf-owner")
        request = CapabilityRequest(
            actor=owner,
            channel=Channel.WORKFLOW,
            tool_name="email_send",
            inputs={"to": "a@example.com", "subject": "x", "body": "y"},
        )
        result = await gate.check(request, injection_flagged=True)
        assert result.allowed is False
        assert result.reason == "injection_flagged"
        events = await CapabilityEventStore(db).list_recent()
        assert len(events) == 1
        assert events[0].decision == "denied"
        assert events[0].injection_flagged is True

    async def test_injection_escalation_requires_confirmation_on_trusted(
        self, db: Database, registry: ToolRegistry
    ) -> None:
        cfg = HestiaConfig.default()
        cfg.trust = TrustConfig.developer()
        gate = make_gate(cfg, db, registry)
        request = CapabilityRequest(
            actor=Identity(platform="telegram", platform_user="owner"),
            channel=Channel.TELEGRAM,
            tool_name="terminal",
            inputs={"command": "whoami"},
        )
        result = await gate.check(request, injection_flagged=True)
        assert result.allowed is True
        assert result.auto_approved is False
        assert result.requires_confirmation is True
        assert result.request_token is not None
        assert len(result.request_token) > 0
        events = await CapabilityEventStore(db).list_recent()
        assert len(events) == 1
        assert events[0].decision == "escalated"
        assert events[0].injection_flagged is True

    async def test_blocked_tool_killswitch_denies(
        self, db: Database, registry: ToolRegistry
    ) -> None:
        cfg = HestiaConfig.default()
        cfg.trust = TrustConfig.developer()
        cfg.trust.blocked_tools = {"terminal"}
        gate = make_gate(cfg, db, registry)
        request = CapabilityRequest(
            actor=Identity(platform="cli", platform_user="owner"),
            channel=Channel.CLI,
            tool_name="terminal",
            inputs={"command": "whoami"},
        )
        result = await gate.check(request)
        assert result.allowed is False
        assert result.reason == "blocked_by_killswitch"

    async def test_subagent_injection_is_denied_non_injection_inherits_trust(
        self, db: Database, registry: ToolRegistry
    ) -> None:
        cfg = HestiaConfig.default()
        cfg.trust = TrustConfig.developer()
        gate = make_gate(cfg, db, registry)
        actor = await make_user(db, "Owner", "subagent", "agent-1", trust_preset="developer")

        injection_request = CapabilityRequest(
            actor=actor,
            channel=Channel.SUBAGENT,
            tool_name="terminal",
            inputs={"command": "whoami"},
        )
        denied = await gate.check(injection_request, injection_flagged=True)
        assert denied.allowed is False
        assert denied.reason == "injection_flagged"

        normal_request = CapabilityRequest(
            actor=actor,
            channel=Channel.SUBAGENT,
            tool_name="terminal",
            inputs={"command": "whoami"},
        )
        approved = await gate.check(normal_request)
        assert approved.allowed is True
        assert approved.auto_approved is True


class TestAllowSideAuditing:
    """L245 item: unattended-channel decisions are audited on ALLOW as well
    as DENY. Under allowlist-only authorization, 'the allowlist let this
    through' is the event worth recording - and today it is silent."""

    async def test_allow_listed_unattended_is_audited(
        self, db: Database, registry: ToolRegistry
    ) -> None:
        cfg = HestiaConfig.default()
        gate = make_gate(cfg, db, registry)
        request = CapabilityRequest(
            actor=Identity(platform="workflow", platform_user="wf-owner"),
            channel=Channel.WORKFLOW,
            tool_name="terminal",
            inputs={"command": "ls"},
            source_workflow_id="wf-1",
        )
        await gate.check(request, allow_list={"terminal"})
        events = await CapabilityEventStore(db).list_recent()
        assert len(events) == 1
        assert events[0].decision == "allowed"
        assert events[0].reason == "allow_listed"

    async def test_non_destructive_approved_on_unattended_is_audited(
        self, db: Database, registry: ToolRegistry
    ) -> None:
        cfg = HestiaConfig.default()
        gate = make_gate(cfg, db, registry)
        request = CapabilityRequest(
            actor=Identity(platform="workflow", platform_user="wf-owner"),
            channel=Channel.SCHEDULER,
            tool_name="read_file",
            inputs={"path": "notes.txt"},
        )
        result = await gate.check(request)
        assert result.allowed is True
        events = await CapabilityEventStore(db).list_recent()
        assert len(events) == 1
        assert events[0].decision == "allowed"

    async def test_trusted_channel_approval_not_audited(
        self, db: Database, registry: ToolRegistry
    ) -> None:
        """Bound audit noise to unattended surfaces; chat approvals stay silent."""
        cfg = HestiaConfig.default()
        gate = make_gate(cfg, db, registry)
        user = await make_user(db, "Chat", "telegram", "chat-user")
        request = CapabilityRequest(
            actor=user,
            channel=Channel.TELEGRAM,
            tool_name="read_file",
            inputs={"path": "notes.txt"},
        )
        await gate.check(request)
        events = await CapabilityEventStore(db).list_recent()
        assert len(events) == 0
