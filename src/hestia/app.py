"""Application bootstrap and context for Hestia CLI."""

from __future__ import annotations

import asyncio
import functools
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import click

from hestia.artifacts.store import ArtifactStore
from hestia.config import HestiaConfig, validate_inference_model_name
from hestia.context.builder import ContextBuilder
from hestia.context.compressor import InferenceHistoryCompressor
from hestia.core.inference import InferenceClient
from hestia.email.adapter import EmailAdapter
from hestia.identity import IdentityCompiler
from hestia.inference import SlotManager
from hestia.memory import MemoryEpochCompiler, MemoryStore
from hestia.memory.handoff import SessionHandoffSummarizer
from hestia.orchestrator import Orchestrator
from hestia.orchestrator.engine import ConfirmCallback
from hestia.persistence.db import Database
from hestia.persistence.failure_store import FailureStore
from hestia.persistence.scheduler import SchedulerStore
from hestia.persistence.sessions import SessionStore
from hestia.persistence.skill_store import SkillStore
from hestia.persistence.trace_store import TraceStore
from hestia.policy.default import DefaultPolicyEngine
from hestia.reflection.runner import ReflectionRunner
from hestia.reflection.scheduler import ReflectionScheduler
from hestia.reflection.store import ProposalStore
from hestia.security import InjectionScanner
from hestia.skills.index import SkillIndexBuilder
from hestia.style.builder import StyleProfileBuilder
from hestia.style.scheduler import StyleScheduler
from hestia.style.store import StyleProfileStore
from hestia.tools.builtin import (
    current_time,
    http_get,
    make_create_scheduled_task_tool,
    make_delegate_task_tool,
    make_delete_memory_tool,
    make_delete_scheduled_task_tool,
    make_disable_scheduled_task_tool,
    make_email_search_and_read_tool,
    make_email_tools,
    make_enable_scheduled_task_tool,
    make_list_dir_tool,
    make_list_memories_tool,
    make_list_scheduled_tasks_tool,
    make_read_artifact_tool,
    make_read_file_tool,
    make_save_memory_tool,
    make_search_memory_tool,
    make_web_search_tool,
    make_write_file_tool,
    search_web,
    terminal,
)
from hestia.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

DEFAULT_CALIBRATION_PATH = Path(__file__).parent.parent.parent / "docs" / "calibration.json"


def _make_policy(cfg: HestiaConfig) -> DefaultPolicyEngine:
    """Build the policy engine from config."""
    return DefaultPolicyEngine(
        ctx_window=cfg.inference.context_length,
        default_reasoning_budget=cfg.inference.default_reasoning_budget,
        trust=cfg.trust,
        config=cfg.policy,
        trust_overrides=cfg.trust_overrides,
    )


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

    async def __call__(self, tool_name: str, arguments: dict[str, Any]) -> bool:
        """Prompt user for confirmation."""
        click.echo(f"\nTool call requested: {tool_name}")
        click.echo(f"Arguments: {arguments}")
        return click.confirm("Execute?", default=True)


@dataclass
class CoreAppContext:
    """Always-available application subsystems."""

    config: HestiaConfig
    db: Database
    session_store: SessionStore
    tool_registry: ToolRegistry
    policy: DefaultPolicyEngine
    memory_store: MemoryStore
    failure_store: FailureStore
    trace_store: TraceStore
    artifact_store: ArtifactStore
    scheduler_store: SchedulerStore
    epoch_compiler: MemoryEpochCompiler
    verbose: bool = False
    confirm_callback: ConfirmCallback | None = None
    calibration_path: Path | None = None
    compiled_identity: str | None = None

    _inference: InferenceClient | None = field(default=None, repr=False)
    _context_builder: ContextBuilder | None = field(default=None, repr=False)
    _slot_manager: SlotManager | None = field(default=None, repr=False)
    _handoff_summarizer: SessionHandoffSummarizer | None = field(
        default=None, repr=False
    )
    _injection_scanner: InjectionScanner | None = field(default=None, repr=False)

    @property
    def inference(self) -> InferenceClient:
        """Lazy inference client — created on first access."""
        if self._inference is None:
            model_name = self.config.inference.model_name.strip()
            if not model_name:
                raise ValueError(
                    "inference.model_name is required — set it to your llama.cpp model "
                    "filename (e.g. 'my-model-Q4_K_M.gguf'), or for tests only set "
                    "HESTIA_ALLOW_DUMMY_MODEL=1 and use model_name='dummy'."
                )
            self._inference = InferenceClient(
                self.config.inference.base_url, model_name
            )
        return self._inference

    @property
    def context_builder(self) -> ContextBuilder:
        """Lazy context builder — created on first access."""
        if self._context_builder is None:
            path = self.calibration_path or DEFAULT_CALIBRATION_PATH
            cb = ContextBuilder.from_calibration_file(
                self.inference, self.policy, path
            )
            if self.compiled_identity:
                cb.set_identity_prefix(self.compiled_identity)
            if self.config.compression.enabled:
                cb.enable_compression(
                    InferenceHistoryCompressor(
                        self.inference, max_chars=self.config.compression.max_chars
                    )
                )
            self._context_builder = cb
        return self._context_builder

    @property
    def slot_manager(self) -> SlotManager:
        """Lazy slot manager — created on first access."""
        if self._slot_manager is None:
            self._slot_manager = SlotManager(
                inference=self.inference,
                session_store=self.session_store,
                slot_dir=self.config.slots.slot_dir,
                pool_size=self.config.slots.pool_size,
            )
        return self._slot_manager

    @property
    def handoff_summarizer(self) -> SessionHandoffSummarizer | None:
        """Lazy handoff summarizer — created on first access if enabled."""
        if self._handoff_summarizer is None and self.config.handoff.enabled:
            self._handoff_summarizer = SessionHandoffSummarizer(
                inference=self.inference,
                memory_store=self.memory_store,
                max_chars=self.config.handoff.max_chars,
                min_messages=self.config.handoff.min_messages,
            )
        return self._handoff_summarizer

    def make_injection_scanner(self) -> InjectionScanner:
        """Create an InjectionScanner from config (cached)."""
        if self._injection_scanner is None:
            self._injection_scanner = InjectionScanner(
                enabled=self.config.security.injection_scanner_enabled,
                entropy_threshold=self.config.security.injection_entropy_threshold,
                skip_filters_for_structured=self.config.security.injection_skip_filters_for_structured,
            )
        return self._injection_scanner


@dataclass
class FeatureAppContext:
    """Optional application subsystems (created only when enabled)."""

    skill_store: SkillStore | None = None
    proposal_store: ProposalStore | None = None
    style_store: StyleProfileStore | None = None
    style_builder: StyleProfileBuilder | None = None
    skill_index_builder: SkillIndexBuilder | None = None

    _reflection_scheduler: ReflectionScheduler | None = field(
        default=None, repr=False
    )
    _style_scheduler: StyleScheduler | None = field(default=None, repr=False)

    @property
    def reflection_scheduler(self) -> ReflectionScheduler | None:
        """Lazy reflection scheduler — created on first access.

        Construction is unconditional so callers can read status/failure
        history even when the scheduler is not auto-started by daemons.
        Whether the scheduler actually ticks is governed by
        ``config.reflection.enabled`` checks at the start sites.
        """
        # This property is accessed via CliAppContext which has config
        # on the core context. We can't build here without config.
        return self._reflection_scheduler

    @property
    def style_scheduler(self) -> StyleScheduler | None:
        """Lazy style scheduler — created on first access if builder is available."""
        return self._style_scheduler


class CliAppContext:
    """Typed application context shared across CLI commands.

    Facade that delegates to :class:`CoreAppContext` and
    :class:`FeatureAppContext`. Keeps command signatures stable
    while allowing phased startup.
    """

    def __init__(
        self,
        core: CoreAppContext,
        features: FeatureAppContext | None = None,
    ) -> None:
        self._core = core
        self._features = features or FeatureAppContext()
        self._bootstrapped = False

    # --- Delegate properties for command compatibility ---

    @property
    def config(self) -> HestiaConfig:
        return self._core.config

    @property
    def db(self) -> Database:
        return self._core.db

    @property
    def session_store(self) -> SessionStore:
        return self._core.session_store

    @property
    def tool_registry(self) -> ToolRegistry:
        return self._core.tool_registry

    @property
    def policy(self) -> DefaultPolicyEngine:
        return self._core.policy

    @property
    def memory_store(self) -> MemoryStore:
        return self._core.memory_store

    @property
    def failure_store(self) -> FailureStore:
        return self._core.failure_store

    @property
    def trace_store(self) -> TraceStore:
        return self._core.trace_store

    @property
    def artifact_store(self) -> ArtifactStore:
        return self._core.artifact_store

    @property
    def scheduler_store(self) -> SchedulerStore:
        return self._core.scheduler_store

    @property
    def epoch_compiler(self) -> MemoryEpochCompiler:
        return self._core.epoch_compiler

    @property
    def verbose(self) -> bool:
        return self._core.verbose

    @property
    def confirm_callback(self) -> ConfirmCallback | None:
        return self._core.confirm_callback

    @confirm_callback.setter
    def confirm_callback(self, callback: ConfirmCallback | None) -> None:
        self._core.confirm_callback = callback

    @property
    def inference(self) -> InferenceClient:
        return self._core.inference

    @property
    def context_builder(self) -> ContextBuilder:
        return self._core.context_builder

    @property
    def slot_manager(self) -> SlotManager:
        return self._core.slot_manager

    @property
    def handoff_summarizer(self) -> SessionHandoffSummarizer | None:
        return self._core.handoff_summarizer

    # --- Feature delegates ---

    @property
    def skill_store(self) -> SkillStore | None:
        return self._features.skill_store

    @property
    def proposal_store(self) -> ProposalStore | None:
        return self._features.proposal_store

    @property
    def style_store(self) -> StyleProfileStore | None:
        return self._features.style_store

    @property
    def style_builder(self) -> StyleProfileBuilder | None:
        return self._features.style_builder

    @property
    def skill_index_builder(self) -> SkillIndexBuilder | None:
        return self._features.skill_index_builder

    @property
    def reflection_scheduler(self) -> ReflectionScheduler | None:
        """Lazy reflection scheduler — created on first access."""
        if self._features._reflection_scheduler is None:
            if self._features.proposal_store is None:
                return None
            runner = ReflectionRunner(
                config=self.config.reflection,
                inference=self.inference,
                trace_store=self.trace_store,
                proposal_store=self._features.proposal_store,
            )
            sched = ReflectionScheduler(
                config=self.config.reflection,
                runner=runner,
                session_store=self.session_store,
            )
            sched.wire_failure_handler(runner)
            self._features._reflection_scheduler = sched
        return self._features._reflection_scheduler

    @property
    def style_scheduler(self) -> StyleScheduler | None:
        """Lazy style scheduler — created on first access if builder is available."""
        if self._features._style_scheduler is None and self._features.style_builder is not None:
            self._features._style_scheduler = StyleScheduler(
                config=self.config.style,
                builder=self._features.style_builder,
                session_store=self.session_store,
            )
        return self._features._style_scheduler

    # --- Methods ---

    def set_confirm_callback(self, callback: ConfirmCallback | None) -> None:
        """Set the tool-confirmation callback used when constructing orchestrators."""
        self._core.confirm_callback = callback

    async def bootstrap_db(self) -> None:
        """Connect to database and create tables. Idempotent."""
        if self._bootstrapped:
            return
        await self.db.connect()
        await self.db.create_tables()
        await self.memory_store.create_table()
        await self.failure_store.create_table()
        await self.trace_store.create_table()
        if self.skill_store is not None:
            await self.skill_store.create_table()
        if self.proposal_store is not None:
            await self.proposal_store.create_table()
        if self.style_store is not None:
            await self.style_store.create_table()
        self._bootstrapped = True

    def make_injection_scanner(self) -> InjectionScanner:
        """Create an InjectionScanner from config."""
        return self._core.make_injection_scanner()

    def make_orchestrator(self) -> Orchestrator:
        """Create an Orchestrator with the current app context."""
        return Orchestrator(
            inference=self.inference,
            session_store=self.session_store,
            context_builder=self.context_builder,
            tool_registry=self.tool_registry,
            policy=self.policy,
            confirm_callback=self.confirm_callback,
            max_iterations=self.config.max_iterations,
            slot_manager=self.slot_manager,
            failure_store=self.failure_store,
            trace_store=self.trace_store,
            handoff_summarizer=self.handoff_summarizer,
            injection_scanner=self.make_injection_scanner(),
            proposal_store=self.proposal_store,
            style_store=self.style_store,
            style_config=self.config.style,
        )


def _require_scheduler_store(app: CliAppContext) -> SchedulerStore:
    """Return the scheduler store or raise a clear error."""
    if app.scheduler_store is None:
        raise click.UsageError(
            "Scheduler is not configured. Set `scheduler.enabled = True` in your config."
        )
    return app.scheduler_store


def make_app(cfg: HestiaConfig) -> CliAppContext:
    """Build subsystems from config and return typed app context."""
    if (
        not cfg.inference.model_name.strip()
        and os.environ.get("HESTIA_ALLOW_DUMMY_MODEL") == "1"
    ):
        cfg.inference.model_name = "dummy"
    validate_inference_model_name(cfg.inference.model_name)

    # Phase 1: Core subsystems (always created)
    db = Database(cfg.storage.database_url)
    artifact_store = ArtifactStore(cfg.storage.artifacts_dir)
    session_store = SessionStore(db)
    policy = _make_policy(cfg)
    memory_store = MemoryStore(db)
    failure_store = FailureStore(db)
    trace_store = TraceStore(db)
    scheduler_store = SchedulerStore(db)
    epoch_compiler = MemoryEpochCompiler(memory_store, max_tokens=500)

    # Honor environment overrides for personality / calibration paths
    env_soul = os.environ.get("HESTIA_SOUL_PATH")
    if env_soul:
        cfg.identity.soul_path = Path(env_soul)
    env_calibration = os.environ.get("HESTIA_CALIBRATION_PATH")
    calibration_path = Path(env_calibration) if env_calibration else DEFAULT_CALIBRATION_PATH

    # Compile identity from SOUL.md when present
    identity_compiler = IdentityCompiler(cfg.identity)
    compiled_identity = identity_compiler.get_compiled_text()

    soul_path = cfg.identity.soul_path
    if soul_path is not None and not soul_path.exists():
        click.echo(
            click.style(
                f"Warning: personality file not found at {soul_path}", fg="yellow"
            ),
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

    # Tool registry with built-in tools
    tool_registry = ToolRegistry(artifact_store)
    tool_registry.register(current_time)
    tool_registry.register(http_get)
    tool_registry.register(make_list_dir_tool(cfg.storage))
    tool_registry.register(terminal)

    # Register file tools with path sandboxing
    tool_registry.register(make_read_file_tool(cfg.storage))
    tool_registry.register(make_write_file_tool(cfg.storage))

    # Register memory tools (bound to the memory store instance)
    tool_registry.register(make_search_memory_tool(memory_store))
    tool_registry.register(make_save_memory_tool(memory_store))
    tool_registry.register(make_list_memories_tool(memory_store))
    tool_registry.register(make_delete_memory_tool(memory_store))
    tool_registry.register(make_read_artifact_tool(artifact_store))

    # Register web search if configured (Tavily)
    web_search_tool = make_web_search_tool(cfg.web_search)
    if web_search_tool is not None:
        tool_registry.register(web_search_tool)
    else:
        # Fallback: DuckDuckGo HTML search (no API key required)
        tool_registry.register(search_web)

    # Register email tools if configured
    for email_tool in make_email_tools(cfg.email):
        tool_registry.register(email_tool)

    email_search_and_read = make_email_search_and_read_tool(EmailAdapter(cfg.email))
    if email_search_and_read is not None:
        tool_registry.register(email_search_and_read)

    if cfg.email.password and not cfg.email.password_env:
        click.echo(
            click.style(
                "Warning: email.password is set in plaintext. Consider using "
                "email.password_env to load it from an environment variable.",
                fg="yellow",
            ),
            err=True,
        )
        logger.warning(
            "email.password is set in plaintext. Consider using email.password_env."
        )

    core = CoreAppContext(
        config=cfg,
        db=db,
        session_store=session_store,
        tool_registry=tool_registry,
        policy=policy,
        memory_store=memory_store,
        failure_store=failure_store,
        trace_store=trace_store,
        artifact_store=artifact_store,
        scheduler_store=scheduler_store,
        epoch_compiler=epoch_compiler,
        verbose=cfg.verbose,
        calibration_path=calibration_path,
        compiled_identity=compiled_identity,
    )

    # Phase 2: Feature subsystems (conditional on config)
    features = FeatureAppContext()

    # Proposal store is lightweight; keep it available for status queries
    # even when reflection auto-tick is disabled.
    features.proposal_store = ProposalStore(db)

    # Style store is also lightweight; commands can query it even when
    # style injection is disabled.
    style_store = StyleProfileStore(db)
    features.style_store = style_store
    features.style_builder = StyleProfileBuilder(db, style_store, cfg.style)

    if os.environ.get("HESTIA_EXPERIMENTAL_SKILLS") == "1":
        skill_store = SkillStore(db)
        features.skill_store = skill_store
        features.skill_index_builder = SkillIndexBuilder(skill_store)

    app = CliAppContext(core=core, features=features)

    # Register scheduler tools (bound to scheduler and session stores)
    if scheduler_store is not None:
        tool_registry.register(
            make_create_scheduled_task_tool(scheduler_store, session_store)
        )
        tool_registry.register(
            make_list_scheduled_tasks_tool(scheduler_store, session_store)
        )
        tool_registry.register(
            make_disable_scheduled_task_tool(scheduler_store, session_store)
        )
        tool_registry.register(
            make_enable_scheduled_task_tool(scheduler_store, session_store)
        )
        tool_registry.register(
            make_delete_scheduled_task_tool(scheduler_store, session_store)
        )

    # Register delegate task tool (needs app for orchestrator factory)
    tool_registry.register(make_delegate_task_tool(session_store, app.make_orchestrator))

    return app


def async_command(coro: Callable[..., Awaitable[Any]]) -> Callable[..., Any]:
    """Decorator for async Click commands.

    Must be used together with ``@click.pass_obj`` so ``app`` is injected
    explicitly by Click rather than hidden inside the decorator.

    Example::

        @cli.command()
        @click.pass_obj
        @async_command
        async def my_cmd(app: CliAppContext, flag: bool) -> None:
            ...
    """

    @functools.wraps(coro)
    def wrapper(app: CliAppContext, *args: Any, **kwargs: Any) -> Any:
        async def _runner() -> Any:
            await app.bootstrap_db()
            return await coro(app, *args, **kwargs)

        return asyncio.run(_runner())

    return wrapper


from hestia.commands.meta import _handle_meta_command  # noqa: E402, F401
