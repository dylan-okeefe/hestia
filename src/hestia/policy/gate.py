"""Capability gate for tool execution requests."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from typing import Any

from hestia.config import HestiaConfig, TrustConfig
from hestia.persistence.capability_events import CapabilityEventStore
from hestia.persistence.users import UserStore
from hestia.policy.channel import Channel
from hestia.policy.identity import Identity
from hestia.tools.capabilities import EMAIL_SEND, SHELL_EXEC, WRITE_LOCAL
from hestia.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_DESTRUCTIVE_CAPABILITIES: frozenset[str] = frozenset({SHELL_EXEC, WRITE_LOCAL, EMAIL_SEND})
_DESTRUCTIVE_TOOL_NAMES: frozenset[str] = frozenset({"browser_login", "delegate_task"})

_TRUSTED_CHANNELS: frozenset[Channel] = frozenset({
    Channel.CLI,
    Channel.TELEGRAM,
    Channel.MATRIX,
    Channel.API,
})
_UNATTENDED_CHANNELS: frozenset[Channel] = frozenset({
    Channel.EMAIL,
    Channel.WEBHOOK,
    Channel.SCHEDULER,
    Channel.WORKFLOW,
})


def _preset_config(name: str) -> TrustConfig:
    """Resolve a preset name to a concrete ``TrustConfig``.

    Unknown names fall back to the paranoid default so the gate stays
    fail-closed even when a user row contains an unexpected preset.
    """
    if name == "paranoid":
        return TrustConfig.paranoid()
    if name == "household":
        return TrustConfig.household()
    if name == "developer":
        return TrustConfig.developer()
    if name == "prompt_on_mobile":
        return TrustConfig.prompt_on_mobile()
    return TrustConfig()


@dataclass
class CapabilityRequest:
    """A request to execute a tool.

    ``actor`` must identify the human sender, not a room or chat id.
    ``source_workflow_id`` and ``source_trigger_id`` are used for audit
    context when the request originates from a workflow or trigger.
    """

    actor: Identity
    channel: Channel
    tool_name: str
    inputs: dict[str, Any]
    session_id: str | None = None
    source_workflow_id: str | None = None
    source_trigger_id: str | None = None


@dataclass
class CapabilityResult:
    """Decision produced by ``CapabilityGate.check``.

    ``requires_confirmation`` is True when the gate itself is escalating to
    an interactive confirmation (e.g. injection-flagged destructive tool on a
    trusted channel). It does not replace the tool-level
    ``requires_confirmation`` flag used by the orchestrator.
    """

    allowed: bool
    auto_approved: bool
    requires_confirmation: bool
    reason: str
    request_token: str | None = None


class CapabilityGate:
    """Single trust/capability boundary for every tool execution path.

    The gate resolves identity, trust preset, tool capabilities, channel
    risk, and injection signals before a tool is allowed to run.
    """

    def __init__(
        self,
        config: HestiaConfig,
        user_store: UserStore | None,
        registry: ToolRegistry,
        event_store: CapabilityEventStore | None = None,
    ) -> None:
        self._config = config
        self._user_store = user_store
        self._registry = registry
        self._event_store = event_store

    def _is_destructive(self, tool_name: str) -> bool:
        """Return True if the tool is in the destructive subset."""
        if tool_name in _DESTRUCTIVE_TOOL_NAMES:
            return True
        try:
            tool_caps = set(self._registry.describe(tool_name).capabilities)
        except Exception:  # noqa: BLE001
            return False
        return bool(tool_caps & _DESTRUCTIVE_CAPABILITIES)

    def _resolve_trust(self, user: Any | None, identity: Identity) -> TrustConfig:
        """Resolve effective trust using the configured precedence."""
        trust = self._config.trust
        if trust.preset is not None:
            trust = _preset_config(trust.preset)
        if user is not None and user.trust_preset is not None:
            trust = _preset_config(user.trust_preset)
        key = f"{identity.platform}:{identity.platform_user}"
        override = self._config.trust_overrides.get(key)
        if override is not None:
            trust = override
        return trust

    @staticmethod
    def _is_auto_approved(tool_name: str, trust: TrustConfig) -> bool:
        approved = trust.auto_approve_tools
        return "*" in approved or tool_name in approved

    async def _audit(
        self,
        request: CapabilityRequest,
        result: CapabilityResult,
        injection_flagged: bool,
    ) -> None:
        if self._event_store is None:
            return
        try:
            await self._event_store.record(
                request,
                result,
                injection_flagged=injection_flagged,
            )
        except Exception as exc:  # noqa: BLE001 — audit must never block execution
            logger.warning("Capability audit failed: %s", exc)

    async def audit_internal(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        reason: str | None,
    ) -> None:
        """Record an explicitly-internal tool invocation (L245 chokepoint).

        The internal mode is an audited escape hatch, not a silent one: every
        use writes a capability_events row with reason="internal:<reason>".
        """
        from hestia.policy.identity import Identity

        request = CapabilityRequest(
            actor=Identity(platform="internal", platform_user="system"),
            channel=Channel.API,
            tool_name=tool_name,
            inputs=dict(arguments),
        )
        result = CapabilityResult(
            allowed=True,
            auto_approved=True,
            requires_confirmation=False,
            reason=f"internal:{reason or 'unspecified'}",
        )
        await self._audit(request, result, injection_flagged=False)

    async def check(
        self,
        request: CapabilityRequest,
        *,
        injection_flagged: bool = False,
        allow_list: set[str] | None = None,
    ) -> CapabilityResult:
        """Evaluate a tool request and return a capability decision.

        Decision order:
        1. Global deny-list / emergency killswitch.
        2. Identity resolution via ``UserStore``.
        3. Effective trust config (``trust_overrides`` → ``User.trust_preset``
           → ``HestiaConfig.trust.preset`` → base config).
        4. Tool capability label plus hard-coded destructive names.
        5. Channel factor: unattended channels gate the destructive subset
           unless the tool is explicitly allow-listed.
        6. Injection escalation: destructive subset requires confirmation on
           trusted channels and is denied on unattended/subagent channels.
        7. Stable confirmation token when escalation requires confirmation.
        8. Audit emit on every deny or escalation.
        """
        allow_list = allow_list or set()

        blocked_tools = getattr(self._config.trust, "blocked_tools", None) or set()
        if request.tool_name in blocked_tools:
            result = CapabilityResult(
                allowed=False,
                auto_approved=False,
                requires_confirmation=False,
                reason="blocked_by_killswitch",
            )
            await self._audit(request, result, injection_flagged)
            return result

        user = None
        if self._user_store is not None:
            try:
                user = await self._user_store.get_user_by_identity(
                    request.actor.platform,
                    request.actor.platform_user,
                )
            except Exception:  # noqa: BLE001 — DB may not be connected in tests
                user = None

        destructive = self._is_destructive(request.tool_name)
        unattended = request.channel in _UNATTENDED_CHANNELS
        if user is None and unattended and destructive:
            if request.tool_name in allow_list and not injection_flagged:
                result = CapabilityResult(
                    allowed=True,
                    auto_approved=True,
                    requires_confirmation=False,
                    reason="allow_listed",
                )
                # L245: allow decisions on unattended channels are audited —
                # under allowlist-only authorization "the allowlist let this
                # through" is exactly the event worth recording.
                await self._audit(request, result, injection_flagged)
                return result
            result = CapabilityResult(
                allowed=False,
                auto_approved=False,
                requires_confirmation=False,
                reason="unknown_actor_untrusted_channel",
            )
            await self._audit(request, result, injection_flagged)
            return result

        if destructive and injection_flagged:
            trusted = request.channel in _TRUSTED_CHANNELS
            if trusted:
                result = CapabilityResult(
                    allowed=True,
                    auto_approved=False,
                    requires_confirmation=True,
                    reason="injection_flagged",
                    request_token=secrets.token_urlsafe(16),
                )
                await self._audit(request, result, injection_flagged)
                return result
            result = CapabilityResult(
                allowed=False,
                auto_approved=False,
                requires_confirmation=False,
                reason="injection_flagged",
            )
            await self._audit(request, result, injection_flagged)
            return result

        if destructive and unattended:
            if request.tool_name in allow_list:
                result = CapabilityResult(
                    allowed=True,
                    auto_approved=True,
                    requires_confirmation=False,
                    reason="allow_listed",
                )
                await self._audit(request, result, injection_flagged)
                return result
            result = CapabilityResult(
                allowed=False,
                auto_approved=False,
                requires_confirmation=False,
                reason="not_allow_listed",
            )
            await self._audit(request, result, injection_flagged)
            return result

        trust = self._resolve_trust(user, request.actor)
        auto_approved = self._is_auto_approved(request.tool_name, trust)
        result = CapabilityResult(
            allowed=True,
            auto_approved=auto_approved,
            requires_confirmation=False,
            reason="approved",
        )
        # L245: non-destructive approvals on unattended channels are audited
        # as well — these are the calls allowlist-only authorization exists
        # to account for. Trusted (attended) channels stay silent: a human
        # is present and the volume would be noise.
        if unattended:
            await self._audit(request, result, injection_flagged)
        return result
