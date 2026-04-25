"""Typed configuration for Hestia."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from hestia.config_env import _ConfigFromEnv


class EmailConfigError(ValueError):
    """Raised when email configuration is invalid."""

    pass


def validate_inference_model_name(model_name: str) -> None:
    """Reject the reserved ``dummy`` model name unless explicitly allowed.

    The literal ``dummy`` is used only in tests behind ``HESTIA_ALLOW_DUMMY_MODEL=1``.
    """
    stripped = model_name.strip()
    if stripped.lower() != "dummy":
        return
    if os.environ.get("HESTIA_ALLOW_DUMMY_MODEL") == "1":
        return
    raise ValueError(
        'inference.model_name "dummy" is reserved for automated tests only. '
        "Configure a real llama.cpp model filename, or set environment variable "
        "HESTIA_ALLOW_DUMMY_MODEL=1 if you intentionally use a dummy model."
    )

# Default location for operator-authored personality (compiled identity; see ADR-0025).
DEFAULT_SOUL_MD_PATH = Path("SOUL.md")


# ---------------------------------------------------------------------------
# Config classes
# ---------------------------------------------------------------------------


@dataclass
class IdentityConfig(_ConfigFromEnv):
    """Configuration for Hestia's personality/identity."""

    _ENV_PREFIX = "IDENTITY"

    soul_path: Path | None = field(
        default_factory=lambda: DEFAULT_SOUL_MD_PATH,
    )  # None = disable; default reads SOUL.md in cwd (DEFAULT_SOUL_MD_PATH)
    compiled_cache_path: Path = field(
        default_factory=lambda: Path(".hestia/compiled_identity.txt")
    )
    max_tokens: int = 300  # Hard cap on compiled view size
    recompile_on_change: bool = True  # Recompile if soul.md changes

    def __post_init__(self) -> None:
        if self.max_tokens < 0:
            raise ValueError(
                f"IdentityConfig.max_tokens must be non-negative, got {self.max_tokens}"
            )


@dataclass
class InferenceConfig(_ConfigFromEnv):
    """Configuration for the llama.cpp inference server."""

    _ENV_PREFIX = "INFERENCE"

    base_url: str = "http://localhost:8001"
    model_name: str = ""
    # Per-slot context budget; should equal llama-server's --ctx-size / --parallel
    context_length: int = 8192
    default_reasoning_budget: int = 2048
    max_tokens: int = 1024

    def __post_init__(self) -> None:
        # Reject the literal placeholder "dummy" at config-load: historically
        # this slipped through and surfaced later as mystifying 404 / "model
        # not found" errors from llama-server. Empty model_name is still
        # allowed here (CLI/setup paths like `hestia doctor` lazily
        # fall back to a placeholder string when they don't need real
        # inference); the real-inference guard lives in
        # InferenceClient.__init__.
        if self.model_name == "dummy" and os.environ.get("HESTIA_ALLOW_DUMMY_MODEL") != "1":
            raise ValueError(
                "inference.model_name == 'dummy' is rejected at config-load — "
                "set it to your real llama.cpp model filename (e.g. "
                "'qwen2.5-7b-instruct-q4_k_m.gguf'), or export "
                "HESTIA_ALLOW_DUMMY_MODEL=1 for CI / test paths that rely on "
                "the placeholder."
            )
        if self.max_tokens < 0:
            raise ValueError(
                f"InferenceConfig.max_tokens must be non-negative, got {self.max_tokens}"
            )


@dataclass
class SlotConfig(_ConfigFromEnv):
    """Configuration for the SlotManager."""

    _ENV_PREFIX = "SLOT"

    slot_dir: Path = field(default_factory=lambda: Path("slots"))
    """Directory where llama-server persists slot snapshots. **Must match
    `llama-server --slot-save-path`.** Hestia sends only the basename to
    llama.cpp; llama-server writes the file here. Hestia itself does not
    write to this directory — it is purely a declaration of where slot
    files will land so that out-of-band cleanup (gc, TTL, etc.) knows
    where to look.
    """
    pool_size: int = 4


@dataclass
class SchedulerConfig(_ConfigFromEnv):
    """Configuration for the Scheduler."""

    _ENV_PREFIX = "SCHEDULER"

    tick_interval_seconds: float = 5.0


@dataclass
class StorageConfig(_ConfigFromEnv):
    """Configuration for persistence and artifact storage."""

    _ENV_PREFIX = "STORAGE"

    database_url: str = "sqlite+aiosqlite:///hestia.db"
    artifacts_dir: Path = field(default_factory=lambda: Path("artifacts"))
    allowed_roots: list[str] = field(default_factory=lambda: ["."])


@dataclass
class TelegramConfig(_ConfigFromEnv):
    """Configuration for the Telegram adapter."""

    _ENV_PREFIX = "TELEGRAM"

    bot_token: str = ""
    allowed_users: list[str] = field(
        default_factory=list
    )  # Empty list denies all users. Populate with user IDs or usernames to allow access.
    rate_limit_edits_seconds: float = 1.5
    http_version: str = "1.1"  # Force HTTP/1.1 for Telegram API stability
    fallback_ips: list[str] = field(
        default_factory=lambda: [
            "149.154.167.220",  # api.telegram.org primary
        ]
    )
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 30.0
    long_poll_timeout_seconds: float = 30.0
    voice_messages: bool = False  # Phase A feature flag


@dataclass
class MatrixConfig(_ConfigFromEnv):
    """Configuration for the Matrix adapter.

    Security: allowed_rooms is a whitelist. Empty list denies all inbound.
    Session mapping: one Matrix room -> one Hestia session (room ID as platform_user).
    """

    _ENV_PREFIX = "MATRIX"

    homeserver: str = "https://matrix.org"
    user_id: str = ""  # Bot MXID e.g., @hestia-bot:matrix.org
    device_id: str = "hestia-bot"
    access_token: str = ""  # From login or admin token
    allowed_rooms: list[str] = field(default_factory=list)  # Room IDs or aliases
    rate_limit_edits_seconds: float = 1.5
    sync_timeout_ms: int = 30000  # Long-poll timeout for /sync


@dataclass
class TrustConfig(_ConfigFromEnv):
    """How much latitude to grant the agent in headless contexts.

    Hestia's threat model for personal-use deployments is "operator is the
    only user; trust the model to act on operator's behalf." This differs
    from multi-tenant SaaS. TrustConfig lets operators pick the posture that
    matches their deployment.

    Defaults here match the `paranoid` preset: safest posture for a fresh
    install or OSS download. Operators should explicitly opt into `household`
    or `developer` via `TrustConfig.household()` / `TrustConfig.developer()`
    in their `config.py`.
    """

    _ENV_PREFIX = "TRUST"

    # Tools that auto-approve without a confirm_callback on headless platforms.
    # When a tool with requires_confirmation=True is called and no confirm_callback
    # is configured (Telegram, Matrix, scheduler), the tool runs anyway iff its
    # name is in this list.
    # Example for household use: ["terminal", "write_file"]
    auto_approve_tools: list[str] = field(default_factory=list)

    # Allow scheduler tick sessions to call SHELL_EXEC-capable tools.
    # When False (default), the policy engine strips shell_exec tools from the
    # model's available tool list during scheduler ticks.
    scheduler_shell_exec: bool = False

    # Allow subagent sessions to call SHELL_EXEC-capable tools.
    subagent_shell_exec: bool = False

    # Allow subagent sessions to call WRITE_LOCAL-capable tools.
    subagent_write_local: bool = False

    # Allow subagent sessions to trigger email_send.
    subagent_email_send: bool = False

    # Allow scheduler ticks to trigger email_send.
    scheduler_email_send: bool = False

    # Active trust preset name (paranoid, household, developer, etc.)
    preset: str | None = None

    @classmethod
    def paranoid(cls) -> TrustConfig:
        """Strictest posture. Current default. Auto-approves nothing; scheduler
        and subagents cannot shell or write."""
        return cls()

    @classmethod
    def household(cls) -> TrustConfig:
        """Recommended posture for single-operator personal deployments.
        Auto-approves terminal and write_file on headless platforms;
        scheduler and subagents can shell and write."""
        return cls(
            auto_approve_tools=["terminal", "write_file"],
            scheduler_shell_exec=True,
            subagent_shell_exec=True,
            subagent_write_local=True,
        )

    @classmethod
    def developer(cls) -> TrustConfig:
        """Most permissive posture. Auto-approves everything;
        all capabilities available everywhere. Intended for development/testing
        only — do not use in a deployment exposed to other users."""
        return cls(
            auto_approve_tools=["*"],  # wildcard — matches any tool name
            scheduler_shell_exec=True,
            subagent_shell_exec=True,
            subagent_write_local=True,
        )

    @classmethod
    def prompt_on_mobile(cls) -> TrustConfig:
        """Mobile-confirmation posture.

        Auto-approves nothing. Every ``requires_confirmation=True`` tool
        routes through the platform's confirm callback before executing.
        Whether the call blocks the conversation thread depends on the
        platform (Telegram inline keyboards block; Matrix reply-pattern
        does not).

        Keeps the rest of the ``household`` defaults: both ``handoff`` and
        ``compression`` are enabled, and scheduler / subagents can shell
        and write.

        Use this when you run Hestia on Telegram or Matrix and want an
        explicit ✅/❌ prompt on your phone for ``terminal``, ``write_file``,
        and ``email_send``.
        """
        return cls(
            auto_approve_tools=[],
            scheduler_shell_exec=True,
            subagent_shell_exec=True,
            subagent_write_local=True,
        )


@dataclass
class HandoffConfig(_ConfigFromEnv):
    """Controls session-close summary generation.

    Disabled by default. When enabled, the orchestrator generates a
    2-3 sentence summary at session close and stores it as a memory
    entry with tag ``handoff``.
    """

    _ENV_PREFIX = "HANDOFF"

    enabled: bool = False
    min_messages: int = 4  # skip very short sessions
    max_chars: int = 350


@dataclass
class CompressionConfig(_ConfigFromEnv):
    """Controls in-turn history compression on overflow.

    Disabled by default. When enabled, the context builder calls a
    :class:`~hestia.context.compressor.HistoryCompressor` on dropped
    messages and splices the summary back into the effective system
    prompt for that turn.
    """

    _ENV_PREFIX = "COMPRESSION"

    enabled: bool = False
    max_chars: int = 400


@dataclass
class EmailConfig(_ConfigFromEnv):
    """Configuration for email integration (IMAP read + SMTP draft/send)."""

    _ENV_PREFIX = "EMAIL"

    imap_host: str = ""
    imap_port: int = 993
    smtp_host: str = ""
    smtp_port: int = 587
    username: str = ""
    password: str = ""  # or app-password
    password_env: str | None = None  # env-var name to read password from
    default_folder: str = "INBOX"
    drafts_folder: str = "Drafts"
    sent_folder: str = "Sent"
    max_fetch: int = 50
    sanitize_html: bool = True
    injection_scan: bool = True  # inherits from SecurityConfig

    @property
    def resolved_password(self) -> str:
        """Return password, preferring password_env if set."""
        if self.password_env:
            import os

            val = os.environ.get(self.password_env)
            if val is None:
                raise EmailConfigError(
                    f"Email password_env '{self.password_env}' is set "
                    "but the environment variable is not defined"
                )
            return val
        return self.password


@dataclass
class SecurityConfig(_ConfigFromEnv):
    """Security-related toggles for Hestia."""

    _ENV_PREFIX = "SECURITY"

    injection_scanner_enabled: bool = True
    injection_entropy_threshold: float = 5.5
    injection_skip_filters_for_structured: bool = True
    egress_audit_enabled: bool = True


@dataclass
class PolicyConfig(_ConfigFromEnv):
    """Configuration for the policy engine."""

    _ENV_PREFIX = "POLICY"

    delegation_keywords: tuple[str, ...] | None = None
    research_keywords: tuple[str, ...] | None = None


@dataclass
class StyleConfig(_ConfigFromEnv):
    """Configuration for the interaction-style profile system."""

    _ENV_PREFIX = "STYLE"

    enabled: bool = False
    min_turns_to_activate: int = 20
    lookback_days: int = 30
    cron: str = "15 3 * * *"

    def __post_init__(self) -> None:
        from croniter import croniter

        try:
            croniter(self.cron)
        except Exception as exc:
            raise ValueError(
                f"StyleConfig.cron is not a valid cron expression: {self.cron}"
            ) from exc


@dataclass
class ReflectionConfig(_ConfigFromEnv):
    """Configuration for the reflection loop (self-improvement during idle hours)."""

    _ENV_PREFIX = "REFLECTION"

    enabled: bool = False
    cron: str = "0 3 * * *"
    idle_minutes: int = 15
    lookback_turns: int = 100
    proposals_per_run: int = 5
    expire_days: int = 14
    model_override: str | None = None  # if operator wants a smaller model

    def __post_init__(self) -> None:
        from croniter import croniter

        try:
            croniter(self.cron)
        except Exception as exc:
            raise ValueError(
                f"ReflectionConfig.cron is not a valid cron expression: {self.cron}"
            ) from exc


@dataclass
class VoiceConfig(_ConfigFromEnv):
    """Configuration for the voice pipeline (STT/TTS)."""

    _ENV_PREFIX = "VOICE"

    stt_model: str = "faster-whisper/large-v3-turbo"
    stt_device: str = "cuda"
    stt_compute_type: str = "int8"
    tts_engine: str = "piper"
    tts_voice: str = "en_US-amy-medium"
    tts_speed: float = 1.0
    model_cache_dir: Path = field(
        default_factory=lambda: Path.home() / ".cache" / "hestia" / "voice"
    )


@dataclass
class WebSearchConfig(_ConfigFromEnv):
    """Configuration for the web_search tool.

    Default `provider=""` disables the tool entirely — it won't register
    in the tool registry if unconfigured. Operators opt in by setting
    provider + api_key in their config.py.
    """

    _ENV_PREFIX = "WEB_SEARCH"

    provider: Literal["tavily", ""] = ""  # "tavily" or "" (disabled)
    api_key: str = ""
    max_results: int = 5
    include_raw_content: bool = False  # Tavily: fetch + extract main content
    search_depth: str = "basic"  # Tavily: "basic" | "advanced"
    time_range: str | None = None  # Tavily: "day" | "week" | "month" | "year" | None


@dataclass
class HestiaConfig(_ConfigFromEnv):
    """Top-level Hestia configuration.

    CLI options override values set here. Config files are loaded
    with HestiaConfig.from_file() and merged with CLI overrides.
    """

    _ENV_PREFIX = "HESTIA"

    inference: InferenceConfig = field(default_factory=InferenceConfig)
    slots: SlotConfig = field(default_factory=SlotConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    matrix: MatrixConfig = field(default_factory=MatrixConfig)
    identity: IdentityConfig = field(default_factory=IdentityConfig)
    trust: TrustConfig = field(default_factory=TrustConfig)
    web_search: WebSearchConfig = field(default_factory=WebSearchConfig)
    handoff: HandoffConfig = field(default_factory=HandoffConfig)
    compression: CompressionConfig = field(default_factory=CompressionConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    reflection: ReflectionConfig = field(default_factory=ReflectionConfig)
    style: StyleConfig = field(default_factory=StyleConfig)
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    trust_overrides: dict[str, TrustConfig] = field(default_factory=dict)
    system_prompt: str = "You are a helpful assistant."
    max_iterations: int = 10
    verbose: bool = False

    @classmethod
    def from_file(cls, path: Path) -> HestiaConfig:
        """Load config from a Python file.

        The file must define a `config` variable of type HestiaConfig.

        .. note::
            The loaded module is executed with ``exec_module`` — treat config
            files as trusted operator-authored code. See ``SECURITY.md``.
        """
        import importlib.util

        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        spec = importlib.util.spec_from_file_location("hestia_config", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load config file: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        config = getattr(module, "config", None)
        if not isinstance(config, HestiaConfig):
            raise TypeError(
                f"Config file must define a `config` variable of type HestiaConfig, "
                f"got {type(config).__name__}"
            )
        validate_inference_model_name(config.inference.model_name)
        return config

    @classmethod
    def for_trust(cls, trust: TrustConfig) -> HestiaConfig:
        """Create a config with handoff/compression implied by the trust preset.

        - ``paranoid()`` → handoff=False, compression=False
        - ``household()`` → handoff=True, compression=True
        - ``developer()`` → handoff=True, compression=True

        Example::

            config = HestiaConfig.for_trust(TrustConfig.household())
        """
        enable = trust not in (TrustConfig.paranoid(), TrustConfig())
        return cls(
            trust=trust,
            handoff=HandoffConfig(enabled=enable),
            compression=CompressionConfig(enabled=enable),
        )

    @classmethod
    def default(cls) -> HestiaConfig:
        return cls()
