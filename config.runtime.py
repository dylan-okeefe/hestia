"""Hestia config for the dedicated runtime worktree (~/Hestia-runtime).

Use: uv run hestia --config config.runtime.py <command>
Data lives under ./runtime-data/ (gitignored).

Telegram (optional for CLI/chat): set HESTIA_TELEGRAM_BOT_TOKEN and
HESTIA_TELEGRAM_ALLOWED_USERS (comma-separated numeric user IDs or usernames).
As of v0.2.0, empty allowed_users **denies all** — you must populate it to let
anyone talk to the bot.

Matrix (optional): loaded from `./.matrix.secrets.py` if present (gitignored).
Copy `.matrix.secrets.example.py` to `.matrix.secrets.py` and fill in. As of
v0.2.0 empty `ALLOWED_ROOMS` **denies all** — populate it before launching.

Trust posture (v0.8.0+): this runtime uses ``TrustConfig.developer()`` —
wildcard auto-approve so destructive tools run without confirmation prompts.
This matches the pre-v0.8.0 behavior the operator was running with on
Telegram + Matrix. Switch to ``prompt_on_mobile()`` if you want explicit
✅/❌ buttons on the phone for ``terminal``, ``write_file``, and
``email_send``; switch to ``household()`` if you want auto-approval for
those three but no wildcard. See ``docs/guides/trust-config.md``.
"""

import importlib.util
import os
from pathlib import Path

from hestia.config import (
    DEFAULT_SOUL_MD_PATH,
    BrowserConfig,
    CompressionConfig,
    EmailConfig,
    HandoffConfig,
    HestiaConfig,
    IdentityConfig,
    InferenceConfig,
    MatrixConfig,
    MemoryConfig,
    ReflectionConfig,
    SchedulerConfig,
    SecurityConfig,
    SlotConfig,
    StorageConfig,
    StyleConfig,
    TelegramConfig,
    TrustConfig,
    VoiceConfig,
    WebConfig,
    WebSearchConfig,
)


def _telegram_from_env() -> TelegramConfig:
    token = os.environ.get("HESTIA_TELEGRAM_BOT_TOKEN", "").strip()
    raw = os.environ.get("HESTIA_TELEGRAM_ALLOWED_USERS", "").strip()
    allowed = [u.strip() for u in raw.split(",") if u.strip()] if raw else []
    return TelegramConfig(
        bot_token=token,
        allowed_users=allowed,
        rate_limit_edits_seconds=4.0,
    )


def _load_matrix_secrets():
    """Load .matrix.secrets.py as a module; return None if missing."""
    p = Path(__file__).resolve().parent / ".matrix.secrets.py"
    if not p.exists():
        return None
    spec = importlib.util.spec_from_file_location("matrix_secrets", p)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _matrix_from_secrets() -> MatrixConfig:
    ms = _load_matrix_secrets()
    if ms is None:
        return MatrixConfig()
    return MatrixConfig(
        homeserver=getattr(ms, "HOMESERVER", "https://matrix.org"),
        user_id=getattr(ms, "USER_ID", ""),
        device_id=getattr(ms, "DEVICE_ID", "hestia-bot"),
        access_token=getattr(ms, "ACCESS_TOKEN", ""),
        allowed_rooms=list(getattr(ms, "ALLOWED_ROOMS", [])),
    )


_ROOT = Path(__file__).resolve().parent / "runtime-data"
_DB_PATH = _ROOT / "hestia.db"

config = HestiaConfig(
    browser=BrowserConfig(
        min_fetch_delay_seconds=3.0,
    ),
    inference=InferenceConfig(
        base_url="http://127.0.0.1:8001",
        model_name="Qwen3.6-35B-A3B-APEX-I-Quality.gguf",
        # Must match llama-server's per-slot context: --ctx-size / --parallel.
        # With -c 393216 -np 3, each slot gets 393216 / 3 = 131072 tokens.
        # The policy engine uses this value for context-window budgeting.
        context_length=131072,
        default_reasoning_budget=2048,
        max_tokens=4096,
        stream=True,
    ),
    slots=SlotConfig(
        # Must match llama-server's --slot-save-path. Hestia sends basenames to
        # llama.cpp (which rejects path separators); this is where those files
        # actually land on disk. Shared with Hermes — that's fine, filenames are
        # session-scoped.
        slot_dir=Path.home() / ".hermes" / "cache" / "slots",
        pool_size=4,
    ),
    scheduler=SchedulerConfig(
        tick_interval_seconds=5.0,
    ),
    storage=StorageConfig(
        database_url=f"sqlite+aiosqlite:///{_DB_PATH}",
        artifacts_dir=_ROOT / "artifacts",
        allowed_roots=[
            "/home/dylan/Documents/Job Search",
            str(_ROOT / "artifacts"),
        ],
    ),
    identity=IdentityConfig(
        soul_path=DEFAULT_SOUL_MD_PATH,
        max_tokens=500,
        capabilities_prefix_enabled=True,
    ),
    memory=MemoryConfig(epoch_max_tokens=2000),
    telegram=_telegram_from_env(),
    matrix=_matrix_from_secrets(),
    voice=VoiceConfig(
        # Use medium whisper model (already cached) instead of large-v3-turbo
        # which requires HuggingFace authentication.
        stt_model="medium",
        # Run STT on CPU to avoid GPU memory contention with llama-server
        # (Qwen3.5-9B uses ~6.2GB of 12GB VRAM; Whisper medium needs ~2-3GB).
        stt_device="cpu",
        stt_compute_type="int8",
        tts_voice="en_US-amy-medium",
    ),
    # Wildcard auto-approve to preserve pre-v0.8.0 "no confirmation prompts"
    # UX on Telegram + Matrix. Also allow scheduler/subagents to send email.
    trust=TrustConfig(
        auto_approve_tools=["*"],
        scheduler_shell_exec=True,
        subagent_shell_exec=True,
        subagent_write_local=True,
        scheduler_email_send=True,
        subagent_email_send=True,
        preset="developer",
    ),
    # Handoff summaries + in-turn compression: enabled because we're on the
    # `developer` trust posture (HestiaConfig.for_trust() would set both).
    handoff=HandoffConfig(enabled=True),
    compression=CompressionConfig(enabled=True),
    # Web search disabled (no Tavily key in .env). To enable:
    #   web_search=WebSearchConfig(provider="tavily", api_key=os.environ["TAVILY_API_KEY"])
    web_search=WebSearchConfig(),
    web=WebConfig(enabled=True, auth_enabled=True, debug_login=False, host="0.0.0.0"),
    # Injection scanner on, default threshold 5.5. Egress audit logs every
    # outbound network call to runtime-data/logs/egress.jsonl.
    security=SecurityConfig(),
    # Gmail via IMAP + SMTP app password from .env (EMAIL_APP_PASSWORD).
    email=EmailConfig(
        imap_host="imap.gmail.com",
        imap_port=993,
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        username="agent.silas13@gmail.com",
        password_env="EMAIL_APP_PASSWORD",
        default_folder="INBOX",
    ),
    # Style profile off — opt-in once the operator wants per-user style learning.
    # Reflection loop off — opt-in once the operator reads the setup guide.
    style=StyleConfig(enabled=False),
    reflection=ReflectionConfig(enabled=False),
    system_prompt=(
        "You are Hestia, a helpful personal assistant.\n\n"
        "You have access to tools. Use the tool-calling format shown in the tool "
        "instructions (the <tool_call> XML format). Place the tool call immediately "
        "after the closing </think> tag and before any conversational text.\n\n"
        "CRITICAL RULES:\n"
        "1. Put all reasoning and planning inside <think></think> blocks.\n"
        "2. If a tool is unavailable, blocked, or returns an error, STOP and tell the user "
        "or choose a different action. Do not keep retrying the same call.\n"
        "3. When the user asks a conversational question, reply directly without calling tools.\n"
        "4. If a website blocks you with CAPTCHA, 'Humans only', or Cloudflare, "
        "STOP trying that site. Use the data you already have.\n"
        "5. When you say you will compile, write, or create something, you MUST "
        "call the appropriate tool (e.g. write_file) to actually do it. Do NOT "
        "just describe what you would do.\n"
        "6. Use concise summaries for tool results. Focus on delivering the final "
        "output the user asked for.\n"
        "7. If you have successfully scraped data from even one source, use it. "
        "Do not keep searching for 'more' sources.\n"
        "8. For LinkedIn, JavaScript-heavy sites, or any page requiring login, "
        "ALWAYS use browser_get — NEVER use terminal with curl. curl cannot "
        "render JavaScript or reuse authenticated sessions.\n"
        "9. If browser_get fails on a site, STOP and tell the user. Do not "
        "fallback to curl or other workarounds.\n"
        "10. STOP after 2-3 searches. Compile and present what you found. Do NOT "
        "keep searching for 'better' or 'more' results.\n"
        "11. If you already have data from a previous search, USE IT. Do not "
        "repeat the same search with slightly different filters.\n"
        "12. If a URL returns 404, STOP guessing alternative URLs on that domain. "
        "Use the data you already have or tell the user the page is gone.\n"
        "13. FILE WRITING: If you need to write more than 2000 characters, create the file "
        "with a short header using write_file, then add each remaining section with "
        "append_to_file. Do NOT try to fit an entire long document into one tool call.\n\n"
        "CHUNKED WRITE EXAMPLE (each call under 2000 chars):\n"
        'write_file({"path": "<listings.md>", "content": "# Job Listings\\n\\n"})\n'
        'append_to_file({"path": "<listings.md>", "content": "## Listing 1\\n..."})\n'
        'append_to_file({"path": "<listings.md>", "content": "## Listing 2\\n..."})\n\n'
        "TOOL EXAMPLES (use the XML format from the tool instructions):\n"
        '- write_file: {"path": "/home/dylan/Documents/notes.md", "content": "# Notes\\n"}\n'
        '- append_to_file: {"path": "/home/dylan/Documents/notes.md", "content": "## Section 1\\n..."}\n'
        '- browser_get: {"url": "https://www.linkedin.com/jobs/search/?keywords=agentic+AI", "wait_seconds": 5}\n'
    ),
    max_iterations=40,
)
