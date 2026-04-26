"""Read-only health checks for Hestia.

Each check is an independent async function that returns a CheckResult.
No check mutates state.  Failures are returned, never raised.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from hestia.app import AppContext


@dataclass(frozen=True)
class CheckResult:
    """Result of a single health check."""

    name: str
    ok: bool
    detail: str  # short human-readable; multi-line OK; "" if ok and trivial


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_checks(app: AppContext) -> list[CheckResult]:
    """Run all health checks against the live app context.

    Order matters only insofar as later checks depend on earlier ones being
    green (e.g. config-loaded before db-readable). Each check is independent
    and never raises; failures are returned as ``CheckResult(ok=False, ...)``.
    """
    checks = [
        _check_python_version,
        _check_dependencies_in_sync,
        _check_config_file_loads,
        _check_config_schema,
        _check_allowed_roots_cwd,
        _check_sqlite_dbs_readable,
        _check_llamacpp_reachable,
        _check_platform_prereqs,
        _check_voice_prerequisites,
        _check_trust_preset_resolves,
        _check_trust_preset_safe_for_production,
        _check_memory_epoch,
    ]
    results: list[CheckResult] = []
    for fn in checks:
        try:
            results.append(await fn(app))
        except Exception as exc:
            # Defensive: every check *should* catch its own exceptions, but if
            # one doesn't we surface it rather than aborting the whole suite.
            results.append(
                CheckResult(
                    name=fn.__name__.replace("_check_", ""),
                    ok=False,
                    detail=f"uncaught {type(exc).__name__}: {exc}",
                )
            )
    return results


def render_results(results: list[CheckResult], *, plain: bool = False) -> str:
    """Format results for terminal output.

    Symbols ✓/✗ unless ``plain=True``, then ``[ok]/[FAIL]``.
    Returns the full multi-line string.
    """
    ok_mark = "[ok]" if plain else "✓"
    fail_mark = "[FAIL]" if plain else "✗"
    lines: list[str] = []
    for r in results:
        mark = ok_mark if r.ok else fail_mark
        lines.append(f"{mark} {r.name}")
        if r.detail:
            for sub in r.detail.splitlines():
                lines.append(f"    {sub}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

async def _check_python_version(app: AppContext) -> CheckResult:
    """Check Python >= 3.11."""
    if sys.version_info >= (3, 11):  # noqa: UP036
        return CheckResult("python_version", True, "")
    got = ".".join(str(x) for x in sys.version_info[:3])
    return CheckResult(
        "python_version",
        False,
        f"Python {got}; need 3.11 or newer",
    )


async def _check_dependencies_in_sync(app: AppContext) -> CheckResult:
    """Run ``uv pip check`` to verify lockfile sync.

    Uses ``asyncio.create_subprocess_exec`` so concurrent ``doctor``
    checks don't stall the event loop for the full 10s ``uv pip check``
    runtime.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "uv",
            "pip",
            "check",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return CheckResult(
            "dependencies_in_sync",
            False,
            "uv not found on PATH; cannot verify dependency sync",
        )
    except Exception as exc:
        return CheckResult(
            "dependencies_in_sync",
            False,
            f"failed to launch uv pip check: {exc}",
        )

    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=10)
    except TimeoutError:
        proc.kill()
        with contextlib.suppress(Exception):
            await proc.communicate()
        return CheckResult(
            "dependencies_in_sync",
            False,
            "uv pip check timed out after 10s",
        )

    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")

    if proc.returncode == 0 and not stdout.strip():
        return CheckResult("dependencies_in_sync", True, "")

    output = stdout.strip() or stderr.strip()
    lines = output.splitlines()[:5]
    return CheckResult(
        "dependencies_in_sync",
        False,
        "\n".join(lines),
    )


async def _check_config_file_loads(app: AppContext) -> CheckResult:
    """Smoke-test that config loaded successfully."""
    if app.config is None:
        return CheckResult("config_file_loads", False, "app.config is None")
    source = getattr(app, "config_source", "<config object provided>")
    return CheckResult("config_file_loads", True, f"loaded from {source}")


async def _check_config_schema(app: AppContext) -> CheckResult:
    """Validate config schema_version when present."""
    # Deferred to L39: add schema_version to HestiaConfig and compare against current.
    version = getattr(app.config, "schema_version", None)
    if version is None:
        return CheckResult(
            "config_schema",
            True,
            "config schema_version not yet defined; pre-0.8.1 config",
        )
    # When schema_version is introduced, compare here.
    return CheckResult("config_schema", True, f"schema_version={version}")


async def _check_allowed_roots_cwd(app: AppContext) -> CheckResult:
    """Warn when ``allowed_roots`` is ``[\".]`` under a broad CWD."""
    roots = app.config.storage.allowed_roots
    if "." not in roots:
        return CheckResult("allowed_roots_cwd", True, "")
    cwd = Path.cwd().resolve()
    home = Path.home().resolve()
    root = Path("/").resolve()
    if cwd in (home, root):
        return CheckResult(
            "allowed_roots_cwd",
            True,
            f"Note: allowed_roots contains '.' while process CWD is {cwd}. "
            "With relative roots this often maps to a very large directory under "
            "systemd --user. Prefer explicit project paths in storage.allowed_roots.",
        )
    return CheckResult("allowed_roots_cwd", True, "")


async def _check_sqlite_dbs_readable(app: AppContext) -> CheckResult:
    """PRAGMA integrity_check on the SQLite database file."""
    db_url = getattr(app.db, "_url", "")
    if not db_url.startswith("sqlite"):
        return CheckResult(
            "sqlite_dbs_readable",
            True,
            f"non-SQLite database ({db_url[:30]}...); skipping integrity check",
        )

    # Parse sqlite+aiosqlite:///path/to/db.db -> /path/to/db.db
    parsed = urlparse(db_url)
    path = parsed.path
    if db_url.startswith("sqlite+aiosqlite://"):
        # On some platforms parsed.path lacks the leading slash; ensure it.
        path = "/" + path.lstrip("/")

    try:
        conn = sqlite3.connect(path)
        cur = conn.execute("PRAGMA integrity_check")
        result = cur.fetchone()
        conn.close()
        if result is not None and result[0].lower() == "ok":
            return CheckResult("sqlite_dbs_readable", True, f"{path}: ok")
        status = result[0] if result else "unknown"
        return CheckResult(
            "sqlite_dbs_readable",
            False,
            f"{path}: {status}",
        )
    except Exception as exc:
        return CheckResult(
            "sqlite_dbs_readable",
            False,
            f"{path}: {exc}",
        )


async def _check_llamacpp_reachable(app: AppContext) -> CheckResult:
    """Hit the llama.cpp /health endpoint when configured.

    Uses ``httpx.AsyncClient`` so the 2 s health-check timeout does not
    block the event loop for other concurrent doctor checks.
    Retains the same error classification as the sync version.
    """
    base_url = app.config.inference.base_url
    if not base_url:
        return CheckResult(
            "llamacpp_reachable",
            True,
            "(no inference base_url configured)",
        )
    health_url = f"{base_url.rstrip('/')}/health"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(health_url)
        if response.status_code == 200:
            return CheckResult("llamacpp_reachable", True, f"{health_url}: 200")
        return CheckResult(
            "llamacpp_reachable",
            False,
            f"llama.cpp at {health_url} returned {response.status_code}",
        )
    except httpx.TimeoutException:
        return CheckResult(
            "llamacpp_reachable",
            False,
            f"llama.cpp at {health_url} did not respond within 2s",
        )
    except httpx.ConnectError:
        return CheckResult(
            "llamacpp_reachable",
            False,
            f"cannot connect to llama.cpp at {health_url}",
        )
    except Exception as exc:
        return CheckResult(
            "llamacpp_reachable",
            False,
            f"{health_url}: {type(exc).__name__}: {exc}",
        )


async def _check_platform_prereqs(app: AppContext) -> CheckResult:
    """Validate that enabled platforms have required credentials."""
    cfg = app.config
    failures: list[str] = []
    enabled: list[str] = []

    # Telegram – enabled when bot_token or allowed_users is set
    if cfg.telegram.bot_token or cfg.telegram.allowed_users:
        enabled.append("telegram")
        if not cfg.telegram.bot_token.strip():
            failures.append("telegram: bot_token not set")

    # Matrix – enabled when user_id, access_token, or allowed_rooms is set
    if cfg.matrix.user_id or cfg.matrix.access_token or cfg.matrix.allowed_rooms:
        enabled.append("matrix")
        if not cfg.matrix.homeserver.strip():
            failures.append("matrix: homeserver not set")
        if not cfg.matrix.user_id.strip():
            failures.append("matrix: user_id not set")
        has_access_token = bool(cfg.matrix.access_token)
        has_password = bool(getattr(cfg.matrix, "password", None))
        password_env = getattr(cfg.matrix, "password_env", None)
        has_password_env = bool(password_env and os.environ.get(password_env))
        if not has_access_token and not has_password and not has_password_env:
            failures.append("matrix: access_token not set")

    # Email – enabled when imap_host, username, or password_env is set
    if cfg.email.imap_host or cfg.email.username or cfg.email.password_env:
        enabled.append("email")
        if not cfg.email.imap_host.strip():
            failures.append("email: imap_host not set")
        if not cfg.email.username.strip():
            failures.append("email: username not set")
        has_password = bool(cfg.email.password)
        has_password_env = bool(cfg.email.password_env and os.environ.get(cfg.email.password_env))
        if not has_password and not has_password_env:
            failures.append("email: password not set and password_env not resolved")

    if failures:
        return CheckResult("platform_prereqs", False, "\n".join(failures))
    if not enabled:
        return CheckResult("platform_prereqs", True, "no platforms configured")
    return CheckResult("platform_prereqs", True, f"enabled: {', '.join(enabled)}")


async def _check_voice_prerequisites(app: AppContext) -> CheckResult:
    """Verify voice dependencies are present when the extra is installed."""
    import importlib.util

    if importlib.util.find_spec("hestia.voice.pipeline") is None:
        return CheckResult(
            "voice_prerequisites",
            True,
            "voice module not available",
        )

    if importlib.util.find_spec("faster_whisper") is None:
        return CheckResult(
            "voice_prerequisites",
            True,
            "voice extra not installed",
        )

    # Verify piper is also present (TTS dependency)
    if importlib.util.find_spec("piper") is None:
        return CheckResult(
            "voice_prerequisites",
            False,
            "faster-whisper present but piper-tts missing; voice extra incomplete",
        )

    return CheckResult(
        "voice_prerequisites",
        True,
        "voice extra installed (faster-whisper + piper-tts)",
    )


async def _check_trust_preset_resolves(app: AppContext) -> CheckResult:
    """Verify trust preset matches a known name."""
    preset = app.config.trust.preset
    if preset is None:
        return CheckResult(
            "trust_preset_resolves",
            True,
            "using custom trust config (no preset name)",
        )
    known = {"paranoid", "household", "developer", "prompt_on_mobile"}
    if preset in known:
        return CheckResult("trust_preset_resolves", True, f"preset='{preset}'")
    return CheckResult(
        "trust_preset_resolves",
        False,
        f"unknown trust preset '{preset}'; known: {', '.join(sorted(known))}",
    )


async def _check_trust_preset_safe_for_production(app: AppContext) -> CheckResult:
    """Fail when the dangerous 'developer' preset is used outside a dev environment."""
    preset = app.config.trust.preset
    if preset != "developer":
        return CheckResult("trust_preset_safe", True, "")
    hestia_env = os.environ.get("HESTIA_ENV", "")
    if hestia_env == "development":
        return CheckResult(
            "trust_preset_safe",
            True,
            "trust preset 'developer' with HESTIA_ENV=development — acknowledged",
        )
    return CheckResult(
        "trust_preset_safe",
        False,
        "Trust preset 'developer' auto-approves all tools. "
        "This is not recommended for production. "
        "Set HESTIA_ENV=development to acknowledge, or switch to a safer preset.",
    )


async def _check_memory_epoch(app: AppContext) -> CheckResult:
    """Check memory epoch file exists and is readable integer."""
    memory_cfg = getattr(app.config, "memory", None)
    if memory_cfg is None:
        return CheckResult(
            "memory_epoch",
            True,
            "memory.epoch_path not configured",
        )
    epoch_path = getattr(memory_cfg, "epoch_path", None)
    if not epoch_path:
        return CheckResult(
            "memory_epoch",
            True,
            "memory.epoch_path not configured",
        )
    try:
        with open(epoch_path) as f:
            content = f.read().strip()
        int(content)
        return CheckResult("memory_epoch", True, f"{epoch_path}: ok")
    except FileNotFoundError:
        return CheckResult(
            "memory_epoch",
            False,
            f"{epoch_path}: file not found",
        )
    except ValueError:
        return CheckResult(
            "memory_epoch",
            False,
            f"{epoch_path}: contents do not parse as int",
        )
    except Exception as exc:
        return CheckResult(
            "memory_epoch",
            False,
            f"{epoch_path}: {exc}",
        )
