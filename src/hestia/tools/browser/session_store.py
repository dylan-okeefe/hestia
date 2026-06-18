"""Persistent browser session storage using Playwright."""

import json
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from hestia.tools.browser.stealth import (
    STEALTH_LAUNCH_ARGS,
    apply_stealth_async,
    stealth_context_kwargs,
)

# Known country-code second-level domains (eTLD patterns)
_KNOWN_CC_SLD = {
    "co.uk",
    "com.au",
    "org.uk",
    "net.au",
    "co.nz",
    "com.br",
    "co.jp",
    "com.cn",
    "co.in",
    "com.mx",
    "co.za",
}


def normalize_domain(hostname: str) -> str:
    """Return the registerable domain (eTLD+1) for a hostname.

    Strips subdomains so that ``www.indeed.com``, ``login.indeed.com``,
    and ``indeed.com`` all map to ``indeed.com``.
    """
    host = hostname.lower().strip()
    if not host:
        return host
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    etld = f"{parts[-2]}.{parts[-1]}"
    if etld in _KNOWN_CC_SLD:
        return f"{parts[-3]}.{etld}"
    return etld


@dataclass
class SessionMetadata:
    """Per-domain browser session metadata."""

    domain: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_saved: datetime | None = None
    last_used: datetime | None = None
    last_health_check: datetime | None = None
    health_status: str = "unknown"  # "healthy", "stale", "expired", "unknown"
    health_check_url: str = ""
    cookie_count: int = 0


class BrowserSessionStore:
    """Manages persistent browser contexts for authenticated sites.

    Stores cookies and localStorage per-domain under
    ``~/.hestia/browser-sessions/<domain>/`` so logins survive restarts.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path.home() / ".hestia" / "browser-sessions"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _safe_name(self, domain: str) -> str:
        return domain.replace(".", "_")

    def _session_dir(self, domain: str, create: bool = True) -> Path:
        path = self.base_dir / self._safe_name(domain)
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def _has_session_data(self, path: Path) -> bool:
        """Return True if *path* contains a stored session file."""
        return path.is_dir() and (
            (path / "cookies.json").exists() or (path / "storage_state.json").exists()
        )

    def _find_existing_dir(self, domain: str) -> Path | None:
        """Return an existing session dir for *domain* or its www variant.

        Tries exact match first, then the domain with/without ``www.`` prefix.
        Only returns directories that actually contain session data.
        Returns ``None`` if no suitable directory exists.
        """
        candidates = [domain]
        if domain.startswith("www."):
            candidates.append(domain[4:])
        else:
            candidates.append("www." + domain)

        for cand in candidates:
            path = self.base_dir / self._safe_name(cand)
            if self._has_session_data(path):
                return path
        return None

    def _metadata_path(self, domain: str) -> Path:
        """Return the path to the metadata.json file for a domain."""
        return self._session_dir(domain) / "metadata.json"

    def _serialize_datetime(self, dt: datetime | None) -> str | None:
        """Serialize a datetime to ISO8601 string."""
        if dt is None:
            return None
        return dt.isoformat()

    def _deserialize_datetime(self, value: str | None) -> datetime | None:
        """Deserialize an ISO8601 string to datetime."""
        if value is None:
            return None
        # Handle both 'Z' suffix and '+00:00'
        value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)

    def save_metadata(self, domain: str, metadata: SessionMetadata) -> None:
        """Save metadata to JSON file."""
        data = asdict(metadata)
        data["created_at"] = self._serialize_datetime(data["created_at"])
        data["last_saved"] = self._serialize_datetime(data["last_saved"])
        data["last_used"] = self._serialize_datetime(data["last_used"])
        data["last_health_check"] = self._serialize_datetime(data["last_health_check"])
        path = self._metadata_path(domain)
        path.write_text(json.dumps(data, indent=2))

    def load_metadata(self, domain: str) -> SessionMetadata | None:
        """Load metadata from JSON file, returning None if missing."""
        path = self._metadata_path(domain)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return SessionMetadata(
                domain=data["domain"],
                created_at=(
                    self._deserialize_datetime(data.get("created_at"))
                    or datetime.now(UTC)
                ),
                last_saved=self._deserialize_datetime(data.get("last_saved")),
                last_used=self._deserialize_datetime(data.get("last_used")),
                last_health_check=self._deserialize_datetime(data.get("last_health_check")),
                health_status=data.get("health_status", "unknown"),
                health_check_url=data.get("health_check_url", ""),
                cookie_count=data.get("cookie_count", 0),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def update_metadata(self, domain: str, **kwargs: Any) -> SessionMetadata | None:
        """Load metadata, update fields, and save back."""
        metadata = self.load_metadata(domain)
        if metadata is None:
            metadata = SessionMetadata(domain=domain)
        for key, value in kwargs.items():
            if hasattr(metadata, key):
                setattr(metadata, key, value)
        self.save_metadata(domain, metadata)
        return metadata

    def save_cookies(self, domain: str, cookies: Sequence[Mapping[str, Any]]) -> None:
        path = self._session_dir(domain) / "cookies.json"
        path.write_text(json.dumps(cookies, indent=2))
        self.update_metadata(
            domain, last_saved=datetime.now(UTC), cookie_count=len(cookies)
        )

    def load_cookies(self, domain: str) -> list[Mapping[str, Any]]:
        # Try exact domain first, then www variant for backward compatibility.
        path = self._session_dir(domain, create=False) / "cookies.json"
        if path.exists():
            return cast(list[Mapping[str, Any]], json.loads(path.read_text()))

        existing_dir = self._find_existing_dir(domain)
        if existing_dir is not None:
            alt_path = existing_dir / "cookies.json"
            if alt_path.exists():
                return cast(list[Mapping[str, Any]], json.loads(alt_path.read_text()))

        return []

    def save_storage(self, domain: str, storage_state: Mapping[str, Any]) -> None:
        path = self._session_dir(domain) / "storage_state.json"
        path.write_text(json.dumps(storage_state, indent=2))
        cookie_count = len(storage_state.get("cookies", []))
        self.update_metadata(
            domain, last_saved=datetime.now(UTC), cookie_count=cookie_count
        )

    def load_storage(self, domain: str) -> dict[str, Any] | None:
        # Try exact domain first, then www variant for backward compatibility.
        path = self._session_dir(domain, create=False) / "storage_state.json"
        if path.exists():
            return cast(dict[str, Any], json.loads(path.read_text()))

        existing_dir = self._find_existing_dir(domain)
        if existing_dir is not None:
            alt_path = existing_dir / "storage_state.json"
            if alt_path.exists():
                return cast(dict[str, Any], json.loads(alt_path.read_text()))

        return None

    def list_domains(self) -> list[str]:
        """Return normalized, deduplicated domains that have session data."""
        domains: set[str] = set()
        for d in self.base_dir.iterdir():
            if d.is_dir() and self._has_session_data(d):
                raw = d.name.replace("_", ".")
                domains.add(normalize_domain(raw))
        return sorted(domains)

    def list_sessions(self) -> list[SessionMetadata]:
        """Return metadata for all domains that have session data.

        Normalizes domain names and merges metadata for directories that
        map to the same normalized domain (e.g. ``www.indeed.com`` and
        ``indeed.com``).
        """
        by_domain: dict[str, SessionMetadata] = {}
        for d in self.base_dir.iterdir():
            if d.is_dir() and self._has_session_data(d):
                raw = d.name.replace("_", ".")
                domain = normalize_domain(raw)
                metadata = self.load_metadata(raw)
                if metadata is None:
                    metadata = SessionMetadata(domain=domain)
                else:
                    metadata.domain = domain

                existing = by_domain.get(domain)
                if existing is None:
                    by_domain[domain] = metadata
                else:
                    # Merge: keep the most recent timestamps
                    if metadata.last_saved and (
                        existing.last_saved is None
                        or metadata.last_saved > existing.last_saved
                    ):
                        existing.last_saved = metadata.last_saved
                    if metadata.last_used and (
                        existing.last_used is None
                        or metadata.last_used > existing.last_used
                    ):
                        existing.last_used = metadata.last_used
                    if metadata.last_health_check and (
                        existing.last_health_check is None
                        or metadata.last_health_check > existing.last_health_check
                    ):
                        existing.last_health_check = metadata.last_health_check
                    # Keep the healthiest status
                    if metadata.health_status == "healthy":
                        existing.health_status = "healthy"
                    elif metadata.health_status != "unknown" and existing.health_status == "unknown":
                        existing.health_status = metadata.health_status
                    if metadata.health_check_url:
                        existing.health_check_url = metadata.health_check_url
                    if metadata.cookie_count > existing.cookie_count:
                        existing.cookie_count = metadata.cookie_count
        return list(by_domain.values())

    def clear(self, domain: str) -> None:
        shutil.rmtree(self._session_dir(domain), ignore_errors=True)

    async def check_health(
        self, domain: str, *, timeout_seconds: int = 30, force: bool = False
    ) -> str:
        """Run a health check on the stored session for a domain.

        Launches a headless browser with the stored session, navigates to the
        health_check_url (default https://domain/), and checks whether the
        session is still authenticated.

        Rate-limited to once per hour per domain unless *force* is True.

        Returns "healthy" or "expired".
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return "unknown"

        metadata = self.load_metadata(domain)
        if metadata is None:
            metadata = SessionMetadata(domain=domain)

        # Rate limiting: enforce minimum 1 hour between automatic checks.
        # Force-checks bypass the throttle.
        if not force and metadata.last_health_check is not None:
            elapsed = datetime.now(UTC) - metadata.last_health_check
            if elapsed.total_seconds() < 3600:
                raise ValueError(
                    f"Health check for {domain} rate-limited. "
                    f"Wait {3600 - int(elapsed.total_seconds())}s before next check."
                )

        health_check_url = metadata.health_check_url or f"https://{domain}/"
        storage_state = self.load_storage(domain)
        if storage_state is None:
            cookies = self.load_cookies(domain)
            if cookies:
                storage_state = {"cookies": cookies, "origins": []}

        status = "unknown"
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=STEALTH_LAUNCH_ARGS,
            )
            context = await browser.new_context(
                **stealth_context_kwargs(storage_state)
            )
            page = await context.new_page()
            await apply_stealth_async(page)
            try:
                await page.goto(
                    health_check_url,
                    timeout=timeout_seconds * 1000,
                    wait_until="networkidle",
                )
                url = page.url
                title = await page.title()

                # Detect login redirects
                login_in_path = any(
                    path in url.lower()
                    for path in ("/login", "/signin", "/auth")
                )
                login_in_title = any(
                    phrase in title.lower()
                    for phrase in ("sign in", "log in", "login")
                )
                status = "expired" if login_in_path or login_in_title else "healthy"

                # Save refreshed cookies/storage_state
                try:
                    refreshed_storage = await context.storage_state()
                    self.save_storage(domain, refreshed_storage)
                    refreshed_cookies = await context.cookies()
                    self.save_cookies(domain, refreshed_cookies)
                except Exception:
                    pass

            except Exception:
                # Navigation or browser errors do not prove the session is
                # expired; the site may block headless access or be unreachable.
                status = "unknown"
            finally:
                await context.close()
                await browser.close()

        metadata.last_health_check = datetime.now(UTC)
        metadata.health_status = status
        self.save_metadata(domain, metadata)
        return status
