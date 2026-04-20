"""Typed configuration for Hestia."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


class EmailConfigError(ValueError):
    """Raised when email configuration is invalid."""

    pass

# Default location for operator-authored personality (compiled identity; see ADR-022).
DEFAULT_SOUL_MD_PATH = Path("SOUL.md")


@dataclass
class IdentityConfig:
    """Configuration for Hestia's personality/identity."""

    soul_path: Path | None = field(
        default_factory=lambda: DEFAULT_SOUL_MD_PATH,
    )  # None = disable; default reads SOUL.md in cwd (DEFAULT_SOUL_MD_PATH)
    compiled_cache_path: Path = field(
        default_factory=lambda: Path(".hestia/compiled_identity.txt")
    )
    max_tokens: int = 300  # Hard cap on compiled view size
    recompile_on_change: bool = True  # Recompile if soul.md changes


@dataclass
class InferenceConfig:
    """Configuration for the llama.cpp inference server."""

    base_url: str = "http://localhost:8001"
    model_name: str = ""
    # Per-slot context budget; should equal llama-server's --ctx-size / --parallel
    context_length: int = 8192
    default_reasoning_budget: int = 2048
    max_tokens: int = 1024


@dataclass
class SlotConfig:
    """Configuration for the SlotManager."""

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
class SchedulerConfig:
    """Configuration for the Scheduler."""

    tick_interval_seconds: float = 5.0


@dataclass
class StorageConfig:
    """Configuration for persistence and artifact storage."""

    database_url: str = "sqlite+aiosqlite:///hestia.db"
    artifacts_dir: Path = field(default_factory=lambda: Path("artifacts"))
    allowed_roots: list[str] = field(default_factory=lambda: ["."])


@dataclass
class TelegramConfig:
    """Configuration for the Telegram adapter."""

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
class MatrixConfig:
    """Configuration for the Matrix adapter.

    Security: allowed_rooms is a whitelist. Empty list denies all inbound.
    Session mapping: one Matrix room -> one Hestia session (room ID as platform_user).
    """

    homeserver: str = "https://matrix.org"
    user_id: str = ""  # Bot MXID e.g., @hestia-bot:matrix.org
    device_id: str = "hestia-bot"
    access_token: str = ""  # From login or admin token
    allowed_rooms: list[str] = field(default_factory=list)  # Room IDs or aliases
    rate_limit_edits_seconds: float = 1.5
    sync_timeout_ms: int = 30000  # Long-poll timeout for /sync

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> MatrixConfig:
        """Load Matrix configuration from environment variables.

        Reads:
            HESTIA_MATRIX_HOMESERVER
            HESTIA_MATRIX_USER_ID
            HESTIA_MATRIX_DEVICE_ID
            HESTIA_MATRIX_ACCESS_TOKEN
            HESTIA_MATRIX_ALLOWED_ROOMS (comma-separated room IDs or aliases)
        """
        import os

        env = environ if environ is not None else os.environ
        allowed_rooms_raw = env.get("HESTIA_MATRIX_ALLOWED_ROOMS", "")
        allowed_rooms = (
            [r.strip() for r in allowed_rooms_raw.split(",") if r.strip()]
            if allowed_rooms_raw
            else []
        )
        return cls(
            homeserver=env.get("HESTIA_MATRIX_HOMESERVER", "https://matrix.org"),
            user_id=env.get("HESTIA_MATRIX_USER_ID", ""),
            device_id=env.get("HESTIA_MATRIX_DEVICE_ID", "hestia-bot"),
            access_token=env.get("HESTIA_MATRIX_ACCESS_TOKEN", ""),
            allowed_rooms=allowed_rooms,
        )


@dataclass
class TrustConfig:
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
class HandoffConfig:
    """Controls session-close summary generation.

    Disabled by default. When enabled, the orchestrator generates a
    2-3 sentence summary at session close and stores it as a memory
    entry with tag ``handoff``.

    Example::

        config = HestiaConfig(
            handoff=HandoffConfig(enabled=True, min_messages=4, max_chars=350),
        )
    """

    enabled: bool = False
    min_messages: int = 4  # skip very short sessions
    max_chars: int = 350


@dataclass
class CompressionConfig:
    """Controls in-turn history compression on overflow.

    Disabled by default. When enabled, the context builder calls a
    :class:`~hestia.context.compressor.HistoryCompressor` on dropped
    messages and splices the summary back into the effective system
    prompt for that turn.

    Example::

        config = HestiaConfig(
            compression=CompressionConfig(enabled=True, max_chars=400),
        )
    """

    enabled: bool = False
    max_chars: int = 400


@dataclass
class EmailConfig:
    """Configuration for email integration (IMAP read + SMTP draft/send)."""

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
class SecurityConfig:
    """Security-related toggles for Hestia."""

    injection_scanner_enabled: bool = True
    injection_entropy_threshold: float = 5.5
    injection_skip_filters_for_structured: bool = True
    egress_audit_enabled: bool = True


@dataclass
class PolicyConfig:
    """Configuration for the policy engine."""

    delegation_keywords: tuple[str, ...] | None = None
    research_keywords: tuple[str, ...] | None = None


@dataclass
class StyleConfig:
    """Configuration for the interaction-style profile system."""

    enabled: bool = False
    min_turns_to_activate: int = 20
    lookback_days: int = 30
    cron: str = "15 3 * * *"


@dataclass
class ReflectionConfig:
    """Configuration for the reflection loop (self-improvement during idle hours)."""

    enabled: bool = False
    cron: str = "0 3 * * *"
    idle_minutes: int = 15
    lookback_turns: int = 100
    proposals_per_run: int = 5
    expire_days: int = 14
    model_override: str | None = None  # if operator wants a smaller model


@dataclass
class VoiceConfig:
    """Configuration for the voice pipeline (STT/TTS)."""

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
class WebSearchConfig:
    """Configuration for the web_search tool.

    Default `provider=""` disables the tool entirely — it won't register
    in the tool registry if unconfigured. Operators opt in by setting
    provider + api_key in their config.py.
    """

    provider: Literal["tavily", ""] = ""  # "tavily" or "" (disabled)
    api_key: str = ""
    max_results: int = 5
    include_raw_content: bool = False  # Tavily: fetch + extract main content
    search_depth: str = "basic"  # Tavily: "basic" | "advanced"
    time_range: str | None = None  # Tavily: "day" | "week" | "month" | "year" | None


@dataclass
class HestiaConfig:
    """Top-level Hestia configuration.

    CLI options override values set here. Config files are loaded
    with HestiaConfig.from_file() and merged with CLI overrides.
    """

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
