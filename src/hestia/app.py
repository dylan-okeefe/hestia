"""Application bootstrap and context for Hestia CLI."""

from __future__ import annotations

import asyncio
import functools
import importlib
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import click

from hestia.artifacts.store import ArtifactStore
from hestia.blocked_actions.digest import BlockedActionsDigest
from hestia.config import HestiaConfig
from hestia.context.builder import ContextBuilder
from hestia.context.compressor import InferenceHistoryCompressor
from hestia.core.inference import InferenceClient
from hestia.core.rate_limiter import SessionRateLimiter
from hestia.core.types import ScheduledTask
from hestia.core.validators import validate_inference_model_name
from hestia.email.adapter import EmailAdapter
from hestia.events.bus import EventBus
from hestia.identity import IdentityCompiler
from hestia.inference import SlotManager
from hestia.memory import MemoryEpochCompiler, MemoryStore
from hestia.memory.compaction_summarizer import SessionCompactionSummarizer
from hestia.memory.maintenance import MemoryMaintenance
from hestia.memory.maintenance.digest import MemoryMaintenanceDigest
from hestia.memory.maintenance.scheduler import (
    ensure_memory_maintenance_tasks as _ensure_memory_maintenance_tasks,
)
from hestia.memory.maintenance.undo import MaintenanceUndo
from hestia.orchestrator import Orchestrator
from hestia.orchestrator.compaction import SessionCompactor
from hestia.orchestrator.engine import ConfirmCallback
from hestia.orchestrator.handoff_service import HandoffService
from hestia.orchestrator.lock import SessionLockManager
from hestia.persistence.capability_events import CapabilityEventStore
from hestia.persistence.db import Database
from hestia.persistence.error_resolution_store import ErrorResolutionStore
from hestia.persistence.failure_store import FailureStore
from hestia.persistence.maintenance_trace_store import MaintenanceTraceStore
from hestia.persistence.message_store import MessageStore
from hestia.persistence.scheduler import SchedulerStore
from hestia.persistence.session_store import SessionStore
from hestia.persistence.trace_store import TraceStore
from hestia.persistence.turn_store import TurnStore
from hestia.persistence.users import UserStore
from hestia.policy.default import DefaultPolicyEngine
from hestia.policy.gate import CapabilityGate
from hestia.reflection.runner import ReflectionRunner
from hestia.reflection.scheduler import ReflectionScheduler
from hestia.reflection.store import ProposalStore
from hestia.security import InjectionScanner
from hestia.style.builder import StyleProfileBuilder
from hestia.style.scheduler import StyleScheduler
from hestia.style.store import StyleProfileStore
from hestia.tools.builtin import (
    browser_get,
    browser_get_json,
    browser_get_links,
    browser_interact,
    browser_login,
    current_time,
    make_accept_proposal_tool,
    make_append_to_file_tool,
    make_blocked_actions_summary_tool,
    make_create_scheduled_task_tool,
    make_defer_proposal_tool,
    make_delegate_task_tool,
    make_delete_memory_tool,
    make_delete_scheduled_task_tool,
    make_disable_scheduled_task_tool,
    make_edit_file_tool,
    make_email_search_and_read_tool,
    make_email_tools,
    make_enable_scheduled_task_tool,
    make_glob_tool,
    make_grep_tool,
    make_http_get_tool,
    make_list_dir_tool,
    make_list_memories_tool,
    make_list_proposals_tool,
    make_list_scheduled_tasks_tool,
    make_read_artifact_tool,
    make_read_file_tool,
    make_reject_proposal_tool,
    make_reset_style_metric_tool,
    make_reset_style_profile_tool,
    make_rollback_turn_tool,
    make_save_memory_tool,
    make_search_memory_tool,
    make_show_proposal_tool,
    make_show_style_profile_tool,
    make_terminal_tool,
    make_web_search_tool,
    make_write_file_tool,
    read_clipboard,
)
from hestia.tools.checkpoint import CheckpointManager
from hestia.tools.external_context import ExternalToolModuleContext
from hestia.tools.registry import ToolRegistry
from hestia.workflows.execution_store import ExecutionStore
from hestia.workflows.store import WorkflowStore

logger = logging.getLogger(__name__)

DEFAULT_CALIBRATION_PATH = Path(__file__).parent.parent.parent / "docs" / "calibration.json"


def _playwright_available() -> bool:
    """Check if Playwright is installed."""
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


def _make_policy(cfg: HestiaConfig) -> DefaultPolicyEngine:
    """Build the policy engine from config."""
    return DefaultPolicyEngine(
        ctx_window=cfg.inference.context_length,
        default_reasoning_budget=cfg.inference.default_reasoning_budget,
        trust=cfg.trust,
        config=cfg.policy,
        trust_overrides=cfg.trust_overrides,
    )


def _build_capabilities_prefix(cfg: HestiaConfig, registry: ToolRegistry) -> str:
    """Build a concise runtime self-awareness block for the system prompt.

    This is intentionally factual and terse: it tells the model exactly what
    deployment, tools, and restrictions it is operating under so it does not
    hallucinate integrations or claim unavailable capabilities.
    """
    from hestia.core.clock import utcnow

    lines = ["Deployment context:"]
    lines.append(f"- Model: {cfg.inference.model_name}")
    lines.append(f"- Context window: {cfg.inference.context_length} tokens per slot; {cfg.slots.pool_size} slots")
    lines.append(f"- Inference endpoint: {cfg.inference.base_url}")

    surfaces = ["CLI"]
    if cfg.telegram.bot_token:
        surfaces.append("Telegram")
    if cfg.matrix.access_token:
        surfaces.append("Matrix")
    if cfg.web.enabled:
        surfaces.append("Web dashboard")
    lines.append(f"- Surfaces: {', '.join(surfaces)}")

    trust_name = cfg.trust.preset or "custom"
    lines.append(f"- Trust posture: {trust_name}")

    tool_names = registry.list_names()
    lines.append(f"- Tools available ({len(tool_names)}): {', '.join(tool_names)}")
    lines.append(
        "- Tool discipline: only call list_tools once if you need it. "
        "The full tool list is provided above and persists for the conversation. "
        "Repeated identical tool calls will be treated as a loop and blocked."
    )

    if cfg.storage.allowed_roots:
        lines.append(f"- Allowed file roots: {', '.join(cfg.storage.allowed_roots)}")

    lines.append(f"- Current time: {utcnow().isoformat()}")

    return "\n".join(lines)


class CliResponseHandler:
    """Handles responses from the orchestrator in CLI mode."""

    def __init__(self, verbose: bool = False):
        """Initialize with verbosity flag."""
        self.verbose = verbose

    async def __call__(self, response: str) -> None:
        """Print response to stdout."""
        click.echo(f"\nAssistant: {response}\n")


class CliConfirmHandler:
    """Handles tool confirmation in CLI mode."""

    async def __call__(self, tool_name: str, arguments: dict[str, Any], request_token: str | None = None) -> bool:
        """Prompt user for confirmation."""
        click.echo(f"\nTool call requested: {tool_name}")
        click.echo(f"Arguments: {arguments}")
        return click.confirm("Execute?", default=True)


class AppContext:
    """Single composition root for Hestia subsystems.

    Replaces the previous three-class split (CoreAppContext +
    FeatureAppContext + CliAppContext facade).  Cheap subsystems are
    created eagerly; expensive or connection-holding subsystems are
    lazy via :func:`functools.cached_property`.
    """

    def __init__(self, config: HestiaConfig) -> None:
        self.config = config
        self.verbose = config.verbose
        self.confirm_callback: ConfirmCallback | None = None
        self._bootstrapped = False
        self._bootstrap_lock = asyncio.Lock()

        # Eager core subsystems
        self.db = Database(config.storage.database_url)
        self.artifact_store = ArtifactStore(config.storage.artifacts_dir)
        self.event_bus = EventBus()
        self.lock_manager = SessionLockManager()
        self.message_store = MessageStore(self.db)
        self.turn_store = TurnStore(self.db)
        self.user_store = UserStore(self.db)
        self.policy = _make_policy(config)
        self.memory_store = MemoryStore(self.db)
        from hestia.memory.topics import TopicStore

        self.topic_store = TopicStore(self.db)
        self.failure_store = FailureStore(self.db)
        self.trace_store = TraceStore(self.db)
        self.scheduler_store = SchedulerStore(self.db)
        self.workflow_store = WorkflowStore(self.db)
        self.execution_store = ExecutionStore(self.db)
        self.error_resolution_store = ErrorResolutionStore(self.db)
        self.capability_event_store = CapabilityEventStore(self.db)
        self.maintenance_trace_store = MaintenanceTraceStore(self.db)
        self.session_store = SessionStore(
            self.db,
            event_bus=self.event_bus,
            message_store=self.message_store,
            memory_store=self.memory_store,
            archive_summarizer=self.compaction_summarizer,
            inference_factory=lambda: self.inference,
        )
        self.handoff_service = HandoffService(self.session_store, self.message_store)
        self.blocked_actions_digest = BlockedActionsDigest(
            self.capability_event_store,
            self.session_store,
        )
        self.trigger_registry: Any = None
        self.epoch_compiler = MemoryEpochCompiler(self.memory_store, max_tokens=self.config.memory.epoch_max_tokens)
        self.tool_registry = ToolRegistry(self.artifact_store)
        self.checkpoint_manager = CheckpointManager()
        self.capability_gate = CapabilityGate(
            config=config,
            user_store=self.user_store,
            registry=self.tool_registry,
            event_store=self.capability_event_store,
        )

        # Eager feature subsystems (lightweight; always available for status queries)
        self.proposal_store = ProposalStore(self.db)
        self.style_store = StyleProfileStore(self.db)
        self.style_builder = StyleProfileBuilder(self.db, self.style_store, config.style)
        self.rate_limiter: SessionRateLimiter | None = None
        if config.rate_limit.enabled:
            self.rate_limiter = SessionRateLimiter(
                rate=config.rate_limit.requests_per_minute / 60.0,
                capacity=config.rate_limit.burst_size,
                max_buckets=config.rate_limit.max_buckets,
            )
        self.email_adapter = EmailAdapter(config.email) if config.email.imap_host else None

        # Private caches for lazy construction
        self._calibration_path: Path | None = None
        self._compiled_identity: str | None = None

    # --- Lazy core subsystems ---

    @functools.cached_property
    def inference(self) -> InferenceClient:
        """Lazy inference client — created on first access."""
        model_name = self.config.inference.model_name.strip()
        if not model_name:
            if os.environ.get("HESTIA_ALLOW_DUMMY_MODEL") == "1":
                model_name = "dummy"
            else:
                raise ValueError(
                    "inference.model_name is required — set it to your llama.cpp model "
                    "filename (e.g. 'my-model-Q4_K_M.gguf'), or for tests only set "
                    "HESTIA_ALLOW_DUMMY_MODEL=1 and use model_name='dummy'."
                )
        return InferenceClient(
            self.config.inference.base_url,
            model_name,
            timeout=self.config.inference.request_timeout,
        )

    @functools.cached_property
    def context_builder(self) -> ContextBuilder:
        """Lazy context builder — created on first access."""
        path = self._calibration_path or DEFAULT_CALIBRATION_PATH
        cb = ContextBuilder.from_calibration_file(self.inference, self.policy, path)
        if self._compiled_identity:
            cb.set_identity_prefix(self._compiled_identity)
        if self.config.identity.capabilities_prefix_enabled:
            cb.set_capabilities_prefix(_build_capabilities_prefix(self.config, self.tool_registry))
        if self.config.compression.enabled:
            cb.enable_compression(
                InferenceHistoryCompressor(self.inference, max_chars=self.config.compression.max_chars)
            )
        return cb

    @functools.cached_property
    def slot_manager(self) -> SlotManager:
        """Lazy slot manager — created on first access."""
        return SlotManager(
            inference=self.inference,
            session_store=self.session_store,
            slot_dir=self.config.slots.slot_dir,
            pool_size=self.config.slots.pool_size,
        )

    @functools.cached_property
    def compaction_summarizer(self) -> SessionCompactionSummarizer:
        """Lazy compaction summarizer for the /compact meta-command."""
        return SessionCompactionSummarizer(
            inference=self.inference,
            memory_store=self.memory_store,
            topic_store=self.topic_store,
            max_chars=self.config.compaction.summary_max_chars,
            min_messages=self.config.compaction.min_messages,
        )

    @functools.cached_property
    def compactor(self) -> SessionCompactor:
        """Lazy session compactor for the /compact meta-command."""
        return SessionCompactor(
            session_store=self.session_store,
            message_store=self.message_store,
            slot_manager=self.slot_manager,
            summarizer=self.compaction_summarizer,
            lock_manager=self.lock_manager,
            config=self.config.compaction,
        )

    @functools.cached_property
    def memory_maintenance(self) -> MemoryMaintenance:
        """Lazy memory maintenance orchestrator."""
        return MemoryMaintenance(
            memory_store=self.memory_store,
            inference=self.inference,
            memory_config=self.config.memory,
            trace_store=self.maintenance_trace_store,
        )

    @functools.cached_property
    def memory_maintenance_digest(self) -> MemoryMaintenanceDigest:
        """Lazy assembler for the memory maintenance digest."""
        return MemoryMaintenanceDigest(
            trace_store=self.maintenance_trace_store,
            session_store=self.session_store,
        )

    @functools.cached_property
    def memory_maintenance_undo(self) -> MaintenanceUndo:
        """Lazy maintenance undo helper."""
        return MaintenanceUndo(
            memory_store=self.memory_store,
            trace_store=self.maintenance_trace_store,
            undo_retention_days=self.config.memory.maintenance.undo_retention_days,
        )

    # --- Lazy feature subsystems ---

    @functools.cached_property
    def reflection_scheduler(self) -> ReflectionScheduler | None:
        """Lazy reflection scheduler — created on first access."""
        runner = ReflectionRunner(
            config=self.config.reflection,
            inference=self.inference,
            trace_store=self.trace_store,
            proposal_store=self.proposal_store,
        )
        sched = ReflectionScheduler(
            config=self.config.reflection,
            runner=runner,
            session_store=self.session_store,
        )
        sched.wire_failure_handler(runner)
        return sched

    @functools.cached_property
    def style_scheduler(self) -> StyleScheduler | None:
        """Lazy style scheduler — created on first access if builder is available."""
        if self.style_builder is not None:
            return StyleScheduler(
                config=self.config.style,
                builder=self.style_builder,
                session_store=self.session_store,
            )
        return None

    # --- Methods ---

    def set_confirm_callback(self, callback: ConfirmCallback | None) -> None:
        """Set the tool-confirmation callback used when constructing orchestrators."""
        self.confirm_callback = callback

    async def bootstrap_db(self) -> None:
        """Connect to database and create tables. Idempotent."""
        # BUG-068: the flag check-then-await window let two concurrent
        # callers both run create_all + migrations. Serialize with a lock.
        if self._bootstrapped:
            return
        async with self._bootstrap_lock:
            if self._bootstrapped:
                return
            await self.db.connect()
            await self.db.create_tables()
            await self.memory_store.create_table()
            await self.failure_store.create_table()
            await self.trace_store.create_table()
            await self.maintenance_trace_store.create_table()
            await self.proposal_store.create_table()
            await self.style_store.create_table()
            await self.workflow_store.create_tables()
            await self.execution_store.create_tables()
            self._bootstrapped = True

    async def ensure_memory_maintenance_tasks(
        self,
        platform: str = "cli",
        platform_user: str = "default",
    ) -> tuple[ScheduledTask, ScheduledTask]:
        """Ensure scheduled maintenance tasks exist for an identity."""
        session = await self.session_store.get_or_create_session(platform, platform_user)
        return await _ensure_memory_maintenance_tasks(
            self.scheduler_store,
            session.id,
            self.config.memory.maintenance,
            platform,
            platform_user,
        )

    def make_injection_scanner(self) -> InjectionScanner:
        """Create an InjectionScanner from config (cached on instance)."""
        return InjectionScanner(
            enabled=self.config.security.injection_scanner_enabled,
            entropy_threshold=self.config.security.injection_entropy_threshold,
            skip_filters_for_structured=self.config.security.injection_skip_filters_for_structured,
        )

    async def start_trigger_registry(self) -> None:
        """Create and start the trigger registry."""
        from hestia.workflows.executor import WorkflowExecutor
        from hestia.workflows.triggers import TriggerRegistry

        async def _execute_workflow(workflow: Any, payload: Any) -> None:
            executor = WorkflowExecutor(self, execution_store=self.execution_store)
            result = await executor.execute(workflow.id, payload)
            logger.info("Workflow %s executed: %s", workflow.id, result.status)

        registry = TriggerRegistry(self.event_bus, self.workflow_store, _execute_workflow)
        await registry.start()
        self.trigger_registry = registry

    async def close(self) -> None:
        """Close lazily-created resources."""
        if "inference" in self.__dict__:
            await self.inference.close()
        if self.email_adapter is not None:
            self.email_adapter.close()

    def make_orchestrator(self) -> Orchestrator:
        """Create an Orchestrator with the current app context."""
        checkpoint_manager: CheckpointManager | None = None
        if self.config.trust.checkpoint_on_edit:
            checkpoint_manager = self.checkpoint_manager

        checkpoint_scope = self.config.storage.checkpoint_scope or None

        handoff_service = HandoffService(
            self.session_store,
            self.message_store,
        )

        return Orchestrator(
            inference=self.inference,
            session_store=self.session_store,
            message_store=self.message_store,
            turn_store=self.turn_store,
            handoff_service=handoff_service,
            context_builder=self.context_builder,
            tool_registry=self.tool_registry,
            policy=self.policy,
            confirm_callback=self.confirm_callback,
            capability_gate=self.capability_gate,
            max_iterations=self.config.max_iterations,
            max_tool_calls_per_turn=self.config.policy.max_tool_calls_per_turn,
            max_tokens=self.config.inference.max_tokens,
            default_reasoning_budget=self.config.inference.default_reasoning_budget,
            slot_manager=self.slot_manager,
            lock_manager=self.lock_manager,
            failure_store=self.failure_store,
            trace_store=self.trace_store,
            injection_scanner=self.make_injection_scanner(),
            proposal_store=self.proposal_store,
            style_store=self.style_store,
            style_config=self.config.style,
            rate_limiter=self.rate_limiter,
            stream=self.config.inference.stream,
            event_bus=self.event_bus,
            checkpoint_manager=checkpoint_manager,
            checkpoint_scope=checkpoint_scope,
            auto_rollback_on_failure=self.config.trust.auto_rollback_on_failure,
        )

    def _register_external_tool_modules(self) -> None:
        """Import and register tools from configured external packages."""
        cfg = self.config
        reg = self.tool_registry
        for dotted_path in cfg.extra_tool_modules:
            try:
                module = importlib.import_module(dotted_path)
            except ImportError as exc:
                logger.warning("Failed to import external tool module %r: %s", dotted_path, exc)
                continue
            setup = getattr(module, "setup", None)
            if callable(setup):
                try:
                    context = ExternalToolModuleContext(db=self.db, config=cfg)
                    setup(context)
                except Exception as exc:  # noqa: BLE001 — external hook failure must not crash startup
                    logger.warning("External tool module %r setup failed: %s", dotted_path, exc)
                    continue
            register = getattr(module, "register", None)
            if register is None or not callable(register):
                logger.warning(
                    "External tool module %r has no callable register() function; skipping",
                    dotted_path,
                )
                continue
            try:
                register(reg)
            except ValueError as exc:
                logger.warning("External tool module %r registration failed: %s", dotted_path, exc)
                continue

    def register_tools(self) -> None:
        """Register built-in and conditional tools."""
        cfg = self.config
        reg = self.tool_registry

        reg.register(current_time)
        reg.register(read_clipboard)
        reg.register(make_http_get_tool(cfg.use_curl_cffi_fallback, cfg.security.egress_audit_enabled))
        reg.register(make_list_dir_tool(cfg.storage))
        reg.register(make_terminal_tool(cfg.trust.blocked_shell_patterns or None))
        reg.register(make_read_file_tool(cfg.storage))
        reg.register(make_write_file_tool(cfg.storage, cfg.trust.write_guard_enabled))
        reg.register(make_append_to_file_tool(cfg.storage))
        reg.register(make_edit_file_tool(cfg.storage))
        reg.register(make_glob_tool(cfg.storage))
        reg.register(make_grep_tool(cfg.storage))
        reg.register(make_rollback_turn_tool(self.checkpoint_manager))
        reg.register(make_blocked_actions_summary_tool(self.blocked_actions_digest))
        reg.register(make_search_memory_tool(self.memory_store))
        reg.register(make_save_memory_tool(self.memory_store, self.topic_store))
        reg.register(make_list_memories_tool(self.memory_store))
        reg.register(make_delete_memory_tool(self.memory_store))
        reg.register(make_read_artifact_tool(self.artifact_store))

        # Proposal tools (bound to proposal store)
        reg.register(make_list_proposals_tool(self.proposal_store))
        reg.register(make_show_proposal_tool(self.proposal_store))
        reg.register(make_accept_proposal_tool(self.proposal_store, event_bus=self.event_bus))
        reg.register(make_reject_proposal_tool(self.proposal_store, event_bus=self.event_bus))
        reg.register(make_defer_proposal_tool(self.proposal_store))

        # Style tools (bound to style store)
        reg.register(make_show_style_profile_tool(self.style_store))
        reg.register(make_reset_style_metric_tool(self.style_store))
        reg.register(make_reset_style_profile_tool(self.style_store))

        web_search_tool = make_web_search_tool(cfg.web_search, cfg.security.egress_audit_enabled)
        if web_search_tool is not None:
            reg.register(web_search_tool)

        for email_tool in make_email_tools(cfg.email, adapter=self.email_adapter):
            reg.register(email_tool)

        email_search_and_read = make_email_search_and_read_tool(self.email_adapter) if self.email_adapter else None
        if email_search_and_read is not None:
            reg.register(email_search_and_read)

        if cfg.email.password and not cfg.email.password_env:
            click.echo(
                click.style(
                    "Warning: email.password is set in plaintext. Consider using "
                    "email.password_env to load it from an environment variable.",
                    fg="yellow",
                ),
                err=True,
            )
            logger.warning("email.password is set in plaintext. Consider using email.password_env.")

        # Scheduler tools (bound to scheduler and session stores)
        if self.scheduler_store is not None:
            reg.register(make_create_scheduled_task_tool(self.scheduler_store, self.session_store))
            reg.register(make_list_scheduled_tasks_tool(self.scheduler_store, self.session_store))
            reg.register(make_disable_scheduled_task_tool(self.scheduler_store, self.session_store))
            reg.register(make_enable_scheduled_task_tool(self.scheduler_store, self.session_store))
            reg.register(make_delete_scheduled_task_tool(self.scheduler_store, self.session_store))

        # Delegate task tool (needs app for orchestrator factory)
        reg.register(make_delegate_task_tool(self.session_store, self.make_orchestrator))

        # Browser tools (only when enabled or Playwright is available)
        if cfg.browser.enabled or _playwright_available():
            reg.register(browser_login)
            reg.register(browser_get)
            reg.register(browser_get_json)
            reg.register(browser_get_links)
            reg.register(browser_interact)

        self._register_external_tool_modules()


# Backward-compatible aliases (deprecated, will be removed in a future release)
CoreAppContext = AppContext
FeatureAppContext = AppContext
CliAppContext = AppContext


def _validate_web_security_posture(cfg: HestiaConfig) -> None:
    """Enforce C1/C3 security guards for the web dashboard.

    Raises HestiaConfigError for hard-fail combinations. Logs a warning for
    the auth-on + exposed + wildcard case so Dylan's runtime keeps booting.
    """
    from hestia.errors import HestiaConfigError
    from hestia.web.auth import is_loopback_host

    if not cfg.web.enabled:
        return

    exposed = not is_loopback_host(cfg.web.host)
    if not exposed or cfg.web.allow_insecure:
        return

    # SEC-006: debug login mints sessions for arbitrary user ids; it must
    # never be silently active on an exposed interface.
    if getattr(cfg.web, "debug_login", False):
        raise HestiaConfigError(
            f"web.debug_login is enabled but web.host is set to the exposed "
            f"interface {cfg.web.host!r}. Debug login allows arbitrary "
            f"user_id sessions. Disable it or set allow_insecure=True to "
            f"accept the risk."
        )

    # C1: auth disabled on an exposed interface is not allowed.
    if not cfg.web.auth_enabled:
        raise HestiaConfigError(
            f"web.auth_enabled is False but web.host is set to the exposed "
            f"interface {cfg.web.host!r}. Either bind to a loopback address "
            f"(e.g. 127.0.0.1), enable web.auth_enabled, or explicitly accept "
            f"the risk by setting web.allow_insecure=True (or "
            f"HESTIA_WEB_ALLOW_INSECURE=1)."
        )

    # C3: wildcard or destructive auto-approval on an exposed interface.
    auto_approve = cfg.trust.auto_approve_tools
    destructive = {"terminal", "write_file", "email_send"}
    flagged = [tool for tool in auto_approve if tool == "*" or tool in destructive]
    if flagged:
        flagged_str = ", ".join(sorted(set(flagged)))
        if cfg.web.auth_enabled:
            logger.warning(
                "web.host=%s is exposed and trust.auto_approve_tools includes "
                "%s. Anyone who can reach the dashboard can invoke destructive "
                "tools without confirmation. Bind to a loopback address or "
                "remove the wildcard/destructive tools from auto_approve_tools. "
                "Set web.allow_insecure=True only if you understand the risk.",
                cfg.web.host,
                flagged_str,
            )
        else:
            # auth_enabled is False here only if allow_insecure is True, which
            # we already checked above, so this branch is defensive.
            raise HestiaConfigError(
                f"web.host={cfg.web.host!r} is exposed and "
                f"trust.auto_approve_tools includes {flagged_str!r}, but "
                f"web.auth_enabled is False. Either enable auth, bind to a "
                f"loopback address, or set web.allow_insecure=True to accept "
                f"the risk."
            )


def _validate_config_at_startup(cfg: HestiaConfig) -> None:
    """Validate config before creating subsystems. Raises HestiaConfigError on failure."""
    from hestia.errors import HestiaConfigError

    # Telegram platform requires a bot token
    if cfg.telegram.bot_token == "" and cfg.matrix.access_token == "":
        # No platform is fully configured — this is okay for CLI-only mode,
        # but warn if the user seems to expect a platform adapter.
        pass

    if cfg.telegram.bot_token == "" and cfg.telegram.allowed_users:
        raise HestiaConfigError(
            "telegram.allowed_users is set but telegram.bot_token is empty. "
            "Set telegram.bot_token to your Telegram bot token."
        )

    _validate_web_security_posture(cfg)

    # Email: if any host is configured, both should be present
    if cfg.email.imap_host or cfg.email.smtp_host:
        if not cfg.email.imap_host:
            raise HestiaConfigError(
                "email.smtp_host is set but email.imap_host is empty. Set email.imap_host to your IMAP server hostname."
            )
        if not cfg.email.smtp_host:
            raise HestiaConfigError(
                "email.imap_host is set but email.smtp_host is empty. Set email.smtp_host to your SMTP server hostname."
            )

    # Database URL: if it's a file path, ensure parent directory exists
    db_url = cfg.storage.database_url
    if db_url.startswith("sqlite") and "://" in db_url:
        # Extract file path from sqlite URL
        path_part = db_url.split("://", 1)[1]
        if path_part and not path_part.startswith(":memory:"):
            db_path = Path(path_part)
            if db_path.parent != Path(".") and not db_path.parent.exists():
                raise HestiaConfigError(
                    f"Database directory does not exist: {db_path.parent}. Create it or update storage.database_url."
                )


def _load_and_validate_config(cfg: HestiaConfig | None = None, config_path: Path | None = None) -> HestiaConfig:
    """Load config from file or default locations, apply env overrides, and validate."""
    if cfg is None:
        cfg = HestiaConfig.from_file(config_path) if config_path else HestiaConfig.default()

    if not cfg.inference.model_name.strip() and os.environ.get("HESTIA_ALLOW_DUMMY_MODEL") == "1":
        cfg.inference.model_name = "dummy"
    validate_inference_model_name(cfg.inference.model_name)
    _validate_config_at_startup(cfg)

    # Environment overrides for personality / calibration paths
    env_soul = os.environ.get("HESTIA_SOUL_PATH")
    if env_soul:
        cfg.identity.soul_path = Path(env_soul)

    return cfg


def _warn_on_missing_files(cfg: HestiaConfig, calibration_path: Path) -> None:
    """Emit warnings when expected personality or calibration files are missing."""
    soul_path = cfg.identity.soul_path
    if soul_path is not None and not soul_path.exists():
        click.echo(
            click.style(f"Warning: personality file not found at {soul_path}", fg="yellow"),
            err=True,
        )
        logger.warning("SOUL.md not found at %s", soul_path)

    if not calibration_path.exists():
        click.echo(
            click.style(
                f"Warning: calibration file not found at {calibration_path} — using defaults",
                fg="yellow",
            ),
            err=True,
        )
        logger.warning("Calibration file not found at %s", calibration_path)


def make_app(cfg: HestiaConfig | None = None, config_path: Path | None = None) -> AppContext:
    """Build subsystems from config and return the application context."""
    cfg = _load_and_validate_config(cfg, config_path)

    env_calibration = os.environ.get("HESTIA_CALIBRATION_PATH")
    calibration_path = Path(env_calibration) if env_calibration else DEFAULT_CALIBRATION_PATH

    app = AppContext(cfg)
    app._calibration_path = calibration_path

    # Compile identity from SOUL.md when present
    identity_compiler = IdentityCompiler(cfg.identity)
    app._compiled_identity = identity_compiler.get_compiled_text()

    _warn_on_missing_files(cfg, calibration_path)
    app.register_tools()

    return app


def _require_scheduler_store(app: AppContext) -> SchedulerStore:
    """Return the scheduler store or raise a clear error."""
    if app.scheduler_store is None:
        raise click.UsageError("Scheduler is not configured. Set `scheduler.enabled = True` in your config.")
    return app.scheduler_store


def async_command(coro: Callable[..., Awaitable[Any]]) -> Callable[..., Any]:
    """Decorator for async Click commands.

    Must be used together with ``@click.pass_obj`` so ``app`` is injected
    explicitly by Click rather than hidden inside the decorator.

    Example::

        @cli.command()
        @click.pass_obj
        @async_command
        async def my_cmd(app: AppContext, flag: bool) -> None:
            ...
    """

    @functools.wraps(coro)
    def wrapper(app: AppContext, *args: Any, **kwargs: Any) -> Any:
        async def _runner() -> Any:
            await app.bootstrap_db()
            return await coro(app, *args, **kwargs)

        return asyncio.run(_runner())

    return wrapper


# Backward-compatible re-export (tests import from app.py)
from hestia.commands.meta import _handle_meta_command  # noqa: E402, F401
from hestia.commands.registry import Command, CommandRegistry  # noqa: E402, F401
