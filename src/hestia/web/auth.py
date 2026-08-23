"""Authentication manager and middleware for the Hestia web dashboard."""

from __future__ import annotations

import ipaddress
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from hestia.config import WebConfig
from hestia.persistence.users import UserStore
from hestia.platforms.base import Platform


def is_loopback_host(host: str) -> bool:
    """Return True if *host* resolves to the loopback interface only.

    Accepts ``localhost``, IPv4 in 127.0.0.0/8 (with optional port), and the
    literal IPv6 ``::1`` address. LAN IPs, IPv4-mapped addresses, empty
    strings, and wildcard binds like ``0.0.0.0`` are treated as exposed
    (return False).
    """
    normalized = host.strip().lower()
    if normalized == "localhost":
        return True
    if not normalized:
        return False

    # Handle [ipv6]:port form.
    if normalized.startswith("["):
        bracket_end = normalized.rfind("]:")
        if bracket_end != -1:
            normalized = normalized[1:bracket_end]
        elif normalized.endswith("]"):
            normalized = normalized[1:-1]
    elif ":" in normalized:
        # Could be IPv6, IPv4:port, or hostname:port. Try parsing as-is first.
        try:
            addr = ipaddress.ip_address(normalized)
        except ValueError:
            # Not a bare address; strip a trailing :port and retry.
            head, _, tail = normalized.rpartition(":")
            if tail.isdigit():
                normalized = head

    try:
        addr = ipaddress.ip_address(normalized)
    except ValueError:
        return False

    # Only the literal ::1 IPv6 address counts as loopback; IPv4-mapped
    # loopback addresses (e.g. ::ffff:127.0.0.1) are treated as exposed.
    if isinstance(addr, ipaddress.IPv6Address):
        return addr.is_loopback and not addr.ipv4_mapped
    return addr.is_loopback


@dataclass
class PendingCode:
    """A one-time code pending verification."""

    platform: str
    platform_user: str
    created_at: datetime
    expires_at: datetime


@dataclass
class WebSession:
    """An authenticated web dashboard session."""

    platform: str
    platform_user: str
    created_at: datetime
    expires_at: datetime
    user_id: str | None = None


@dataclass
class RateLimitWindow:
    """Tracks failed attempts for a single IP."""

    attempts: list[datetime] = field(default_factory=list)

    def prune(self, window: timedelta = timedelta(minutes=10)) -> None:
        """Remove attempts older than the window."""
        now = datetime.now(UTC)
        self.attempts = [t for t in self.attempts if now - t < window]

    def is_blocked(self, max_attempts: int = 5) -> bool:
        """Return True if this IP has exceeded the allowed failures."""
        self.prune()
        return len(self.attempts) >= max_attempts

    def record(self) -> None:
        """Record a new failed attempt."""
        self.attempts.append(datetime.now(UTC))


class AuthManager:
    """Manages one-time codes and sessions for web dashboard auth."""

    def __init__(
        self,
        adapters: dict[str, Platform],
        config: WebConfig,
        user_store: UserStore | None = None,
    ) -> None:
        self.adapters = adapters
        self.config = config
        self._user_store = user_store
        self._pending_codes: dict[str, PendingCode] = {}
        self._sessions: dict[str, WebSession] = {}
        self._rate_limits: dict[str, RateLimitWindow] = {}
        self._code_request_limits: dict[str, list[datetime]] = {}

    def generate_code(self) -> str:
        """Generate a cryptographically random numeric code."""
        return str(secrets.randbelow(10**self.config.code_length)).zfill(self.config.code_length)

    def _get_configured_user(self, platform: str) -> str:
        """Return the single configured user for a platform.

        Raises ValueError if the platform is not available or does not have
        exactly one configured user.
        """
        adapter = self.adapters.get(platform)
        if adapter is None:
            raise ValueError(f"Platform {platform!r} is not configured or running")

        if platform == "telegram":
            users: list[str] = adapter._config.allowed_users  # type: ignore[attr-defined]
        elif platform == "matrix":
            users = adapter._config.allowed_rooms  # type: ignore[attr-defined]
        else:
            raise ValueError(f"Unsupported platform {platform!r}")

        if len(users) == 0:
            raise ValueError(f"Platform {platform!r} has no configured users")

        user: str = users[0]
        return user

    def _cleanup_stale_entries(self) -> None:
        """Remove old entries from rate limit tracking dicts."""
        now = datetime.now(UTC)
        # Clean up verification rate limits
        for ip, window in list(self._rate_limits.items()):
            window.prune()
            if not window.attempts:
                del self._rate_limits[ip]
        # Clean up code request limits (5-minute window)
        for ip, timestamps in list(self._code_request_limits.items()):
            self._code_request_limits[ip] = [t for t in timestamps if now - t < timedelta(minutes=5)]
            if not self._code_request_limits[ip]:
                del self._code_request_limits[ip]
        # Clean up expired pending codes
        for code, pending in list(self._pending_codes.items()):
            if pending.expires_at < now:
                del self._pending_codes[code]
        # Clean up expired sessions
        for token, session in list(self._sessions.items()):
            if session.expires_at < now:
                del self._sessions[token]

    def check_code_request_limit(self, ip: str) -> bool:
        """Check whether the IP has exceeded code request rate limit.

        Returns False if blocked (≥3 requests in 5 minutes), True otherwise.
        """
        now = datetime.now(UTC)
        timestamps = self._code_request_limits.get(ip, [])
        timestamps = [t for t in timestamps if now - t < timedelta(minutes=5)]
        return len(timestamps) < 3

    def code_request_retry_after(self, ip: str) -> int:
        """Return seconds until the IP can request another code."""
        now = datetime.now(UTC)
        timestamps = self._code_request_limits.get(ip, [])
        if not timestamps:
            return 0
        oldest = min(timestamps)
        retry = int((oldest + timedelta(minutes=5) - now).total_seconds())
        return max(0, retry)

    def _is_authorized_recipient(self, platform: str, platform_user: str) -> bool:
        """SEC-002: only allowlisted identities may receive login codes.

        A client-supplied recipient used to be delivered to verbatim, letting
        anyone point codes at arbitrary chat IDs.
        """
        if platform == "telegram":
            users: list[str] = self.adapters[platform]._config.allowed_users  # type: ignore[attr-defined]
        elif platform == "matrix":
            users = self.adapters[platform]._config.allowed_rooms  # type: ignore[attr-defined]
        else:
            return False
        normalized = {u.lstrip("@").lower() for u in users}
        candidate = platform_user.lstrip("@").lower()
        return candidate in normalized

    async def request_code(self, platform: str, platform_user: str | None = None) -> dict[str, Any]:
        """Generate and send a one-time code via the requested platform.

        Returns a dict with status information.
        """
        self._cleanup_stale_entries()

        if platform_user is not None and not self._is_authorized_recipient(
            platform, platform_user
        ):
            raise ValueError("Requested recipient is not an authorized user")
        if platform_user is None:
            platform_user = self._get_configured_user(platform)
        adapter = self.adapters[platform]

        code = self.generate_code()
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=self.config.code_expiry_seconds)

        self._pending_codes[code] = PendingCode(
            platform=platform,
            platform_user=platform_user,
            created_at=now,
            expires_at=expires_at,
        )

        await adapter.send_message(platform_user, f"Your Hestia dashboard code is: {code}")

        return {
            "status": "sent",
            "platform": platform,
            "expires_in": self.config.code_expiry_seconds,
        }

    def is_rate_limited(self, ip: str) -> bool:
        """Check if the IP is currently rate-limited."""
        return self._is_rate_limited(ip)

    def _is_rate_limited(self, ip: str) -> bool:
        """Check whether the IP is currently rate-limited."""
        window = self._rate_limits.get(ip)
        if window is None:
            return False
        return window.is_blocked()

    def _record_failed_attempt(self, ip: str) -> None:
        """Record a failed verification attempt from an IP."""
        if ip not in self._rate_limits:
            self._rate_limits[ip] = RateLimitWindow()
        self._rate_limits[ip].record()

    async def debug_login(self, user_id: str) -> tuple[str, WebSession] | None:
        """Create a session directly for a user without code verification.

        Used when web.debug_login is enabled. Looks up the user's first
        identity and creates a session token immediately.

        Returns (token, WebSession) on success, or None if the user has
        no identities.
        """
        self._cleanup_stale_entries()

        if self._user_store is None:
            return None

        identities = await self._user_store.get_identities(user_id)
        if not identities:
            return None

        identity = identities[0]
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=self.config.session_lifetime_hours)

        session = WebSession(
            platform=identity.platform,
            platform_user=identity.platform_user,
            created_at=now,
            expires_at=expires_at,
            user_id=user_id,
        )
        self._sessions[token] = session
        return (token, session)

    async def validate_code(self, code: str, ip: str) -> tuple[str, WebSession] | None:
        """Validate a one-time code and create a session if valid.

        Returns (token, WebSession) on success, or None if the code is invalid,
        expired, or the IP is rate-limited.
        """
        self._cleanup_stale_entries()

        if self._is_rate_limited(ip):
            return None

        pending = self._pending_codes.pop(code, None)
        if pending is None:
            self._record_failed_attempt(ip)
            return None

        if pending.expires_at < datetime.now(UTC):
            self._record_failed_attempt(ip)
            return None

        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=self.config.session_lifetime_hours)

        user_id = None
        if self._user_store is not None:
            user = await self._user_store.get_user_by_identity(pending.platform, pending.platform_user)
            if user is not None:
                user_id = user.id

        session = WebSession(
            platform=pending.platform,
            platform_user=pending.platform_user,
            created_at=now,
            expires_at=expires_at,
            user_id=user_id,
        )
        self._sessions[token] = session
        return (token, session)

    def get_session(self, token: str) -> WebSession | None:
        """Return a session by token, or None if not found or expired."""
        session = self._sessions.get(token)
        if session is None:
            return None
        if session.expires_at < datetime.now(UTC):
            self.remove_session(token)
            return None
        return session

    def remove_session(self, token: str) -> bool:
        """Remove a session. Returns True if it existed."""
        return self._sessions.pop(token, None) is not None

    def validate_token(self, token: str) -> tuple[str, WebSession | None]:
        """Validate a session token.

        Returns ("valid", session) on success, ("missing", None) if the token
        does not exist, or ("expired", None) if the session has expired.
        """
        session = self._sessions.get(token)
        if session is None:
            return ("missing", None)
        if session.expires_at < datetime.now(UTC):
            self.remove_session(token)
            return ("expired", None)
        return ("valid", session)


class AuthMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that enforces Bearer token auth on API routes."""

    def __init__(self, app: Any, auth_manager: AuthManager, web_config: WebConfig) -> None:
        super().__init__(app)
        self.auth_manager = auth_manager
        self.web_config = web_config

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        # Skip non-API routes, auth routes, and public health checks
        if (
            not path.startswith("/api/")
            or path.startswith("/api/auth/")
            or path.startswith("/api/webhooks/")
            or path == "/api/health"
        ):
            return await call_next(request)

        # Skip if auth disabled
        if not self.web_config.auth_enabled:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse({"detail": "Authentication required"}, status_code=401)

        token = auth_header[7:]
        status, session = self.auth_manager.validate_token(token)

        if status == "missing":
            return JSONResponse({"detail": "Authentication required"}, status_code=401)
        if status == "expired":
            return JSONResponse({"detail": "Session expired"}, status_code=401)

        assert session is not None
        request.state.platform = session.platform
        request.state.platform_user = session.platform_user
        request.state.user_id = session.user_id
        return await call_next(request)


def add_auth_middleware(app: Any, auth_manager: AuthManager, web_config: WebConfig) -> None:
    """Register the auth middleware on a FastAPI application."""
    app.add_middleware(AuthMiddleware, auth_manager=auth_manager, web_config=web_config)
