"""Shared authenticated browser fetch helper."""

from __future__ import annotations

import asyncio
import atexit
import logging
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

from playwright.async_api import async_playwright

from hestia.security.ssrf import SSRFBlockedError, assert_url_safe
from hestia.tools.browser.session_store import BrowserSessionStore, SessionMetadata
from hestia.tools.browser.stealth import (
    STEALTH_LAUNCH_ARGS,
    apply_stealth_async,
    stealth_context_kwargs,
)
from hestia.tools.result_classifier import ToolResultCategory

logger = logging.getLogger(__name__)

_LOGIN_PATHS = ("/login", "/signin", "/auth", "/checkpoint")
_LOGIN_PHRASES = (
    "sign in",
    "log in",
    "login",
    "verify your identity",
    "checkpoint",
    "welcome back",
)
_BOT_PHRASES = (
    "additional verification required",
    "cloudflare",
    "captcha",
)
_NOT_FOUND_PHRASES = (
    "404",
    "not found",
    "page doesn't exist",
    "page is gone",
)


#: Number of login-phrase occurrences in the body that indicate a login/challenge
#: page rather than a content page that happens to mention logging in.
_LOGIN_BODY_OCCURRENCE_THRESHOLD = 3



@dataclass
class BrowserFetchResult:
    """Result of an authenticated browser fetch."""

    ok: bool
    category: ToolResultCategory
    text: str
    links: list[dict[str, Any]] = field(default_factory=list)
    final_url: str = ""
    title: str = ""


def _get_min_delay_seconds() -> float:
    """Return the minimum delay between fetches for the same domain."""
    from hestia.config import BrowserConfig

    return BrowserConfig.from_env().min_fetch_delay_seconds


async def _rate_limit_sleep(metadata: SessionMetadata | None) -> None:
    """Sleep if the last fetch for *domain* was too recent."""
    if metadata is None or metadata.last_used is None:
        return

    elapsed = (datetime.now(UTC) - metadata.last_used).total_seconds()
    min_delay = _get_min_delay_seconds()
    sleep_seconds = min_delay - elapsed + random.uniform(0.0, 0.5)
    if sleep_seconds > 0:
        logger.debug(
            "Rate-limiting fetch for %s (elapsed %.2fs, min_delay %.2fs, sleep %.2fs)",
            metadata.domain if metadata.domain else "unknown",
            elapsed,
            min_delay,
            sleep_seconds,
        )
        await asyncio.sleep(sleep_seconds)


def _load_session(store: BrowserSessionStore, domain: str) -> dict[str, Any] | None:
    """Load storage_state for domain, falling back to cookies.json."""
    storage = store.load_storage(domain)
    if storage is not None:
        return storage

    cookies = store.load_cookies(domain)
    if cookies:
        logger.debug("No storage_state for %s; falling back to cookies.json", domain)
        return {"cookies": cookies, "origins": []}

    return None


async def _extract_text(page: Any) -> str:
    """Extract readable text from the page, stripping scripts/styles/modals."""
    result = await page.evaluate(
        """() => {
            document.querySelectorAll(
                "script, style, nav, footer, iframe, noscript, aside, " +
                "[aria-modal='true'], [role='dialog'], .artdeco-modal, .artdeco-modal-overlay"
            ).forEach(el => el.remove());
            return document.body.innerText || "";
        }"""
    )
    return str(result) if result is not None else ""


async def _extract_links(page: Any, selector: str, pattern: str) -> list[dict[str, Any]]:
    """Extract hyperlinks from *page* matching *selector* and optional *pattern*."""
    result = await page.evaluate(
        """({selector, pattern}) => {
            const re = pattern ? new RegExp(pattern, 'i') : null;
            const seen = new Set();
            const results = [];
            document.querySelectorAll(selector).forEach(el => {
                const href = el.href || el.closest('a')?.href;
                if (!href) return;
                const text = (el.innerText || el.textContent || '').trim();
                if (re && !re.test(text)) return;
                if (seen.has(href)) return;
                seen.add(href);
                results.push({text: text.slice(0, 200), href: href});
            });
            return results;
        }""",
        {"selector": selector, "pattern": pattern},
    )
    return result if isinstance(result, list) else []


def _format_failure_message(category: ToolResultCategory, message: str) -> str:
    """Prefix a failure message with its structured category for downstream consumers."""
    return f"[CATEGORY: {category.name}] {message}"


def _classify_page(url: str, title: str, text: str) -> tuple[bool, ToolResultCategory, str]:
    """Detect login/bot/not-found pages and return a failure description.

    Decisions are driven primarily by the final URL, HTTP status (handled in
    ``fetch_url``), and page title.  Body text is treated as a login/challenge
    page only when it is dominated by login UI or corroborated by the URL or
    title, so content like "Log in to apply" on a job listing is not discarded.

    Returns ``(is_blocked, category, message)``.
    """
    lower_url = url.lower()
    lower_title = title.lower()
    lower_text = text.lower()

    # 1. Final URL points at a login/checkpoint gate.
    if any(path in lower_url for path in _LOGIN_PATHS):
        return (
            True,
            ToolResultCategory.BLOCKED,
            _format_failure_message(
                ToolResultCategory.BLOCKED,
                f"[BLOCKED - LOGIN_REQUIRED] Fetched {url} redirected to login or "
                f"checkpoint page ({url}). Re-authenticate with browser_login.",
            ),
        )

    # 2. Page title clearly indicates a login/challenge page.
    if any(phrase in lower_title for phrase in _LOGIN_PHRASES):
        return (
            True,
            ToolResultCategory.BLOCKED,
            _format_failure_message(
                ToolResultCategory.BLOCKED,
                f"[BLOCKED - LOGIN_REQUIRED] Fetched {url} presented a login or "
                f"challenge page ({url}). Re-authenticate with browser_login.",
            ),
        )

    if not lower_text:
        return False, ToolResultCategory.SUCCESS, ""

    # 3. Bot protection is usually explicit in the body.
    if any(phrase in lower_text for phrase in _BOT_PHRASES):
        return (
            True,
            ToolResultCategory.BLOCKED,
            _format_failure_message(
                ToolResultCategory.BLOCKED,
                f"[BLOCKED] Bot protection page for {url} ({url}). "
                "The site is blocking automated access.",
            ),
        )

    # 4. Body text only counts as a login page when login phrases dominate.
    #    A single mention in a long listing is not enough.
    login_occurrences = sum(lower_text.count(phrase) for phrase in _LOGIN_PHRASES)
    dominated_by_login_ui = (
        login_occurrences >= _LOGIN_BODY_OCCURRENCE_THRESHOLD
        or (len(text) < 200 and login_occurrences >= 1)
    )
    if dominated_by_login_ui:
        return (
            True,
            ToolResultCategory.BLOCKED,
            _format_failure_message(
                ToolResultCategory.BLOCKED,
                f"[BLOCKED - LOGIN_REQUIRED] Fetched {url} presented a login or "
                f"challenge page ({url}). Re-authenticate with browser_login.",
            ),
        )

    # 5. 404-like body text is only trusted when corroborated by URL or title.
    url_not_found = "/404" in lower_url
    title_not_found = any(phrase in lower_title for phrase in _NOT_FOUND_PHRASES)
    if url_not_found or title_not_found:
        return (
            True,
            ToolResultCategory.NOT_FOUND,
            _format_failure_message(
                ToolResultCategory.NOT_FOUND,
                f"[NOT FOUND] {url} returned 404 or page not found.",
            ),
        )

    return False, ToolResultCategory.SUCCESS, ""


class _BrowserPool:
    """Lazy, process-scoped pool that keeps one warm Playwright browser open.

    Creating a browser per fetch is expensive; this pool amortizes launch cost
    across calls while isolating sessions per domain in separate contexts.
    """

    def __init__(self) -> None:
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._lock = asyncio.Lock()

    async def _start(self) -> None:
        if self._browser is not None:
            return
        p = await async_playwright().__aenter__()
        try:
            browser = await p.chromium.launch(
                headless=True,
                args=STEALTH_LAUNCH_ARGS,
            )
        except Exception:
            await p.stop()
            raise
        self._playwright = p
        self._browser = browser

    async def new_context(self, storage_state: dict[str, Any] | None) -> Any:
        async with self._lock:
            await self._start()
        assert self._browser is not None
        return await self._browser.new_context(**stealth_context_kwargs(storage_state))

    async def close_context(self, context: Any) -> None:
        try:
            await context.close()
        except Exception as exc:
            logger.warning("Error closing browser context: %s", exc)

    async def close(self) -> None:
        async with self._lock:
            if self._browser is not None:
                try:
                    await self._browser.close()
                except Exception as exc:
                    logger.warning("Error closing browser: %s", exc)
                self._browser = None
            if self._playwright is not None:
                try:
                    await self._playwright.stop()
                except Exception as exc:
                    logger.warning("Error stopping playwright: %s", exc)
                self._playwright = None


_pool = _BrowserPool()


def _close_browser_pool_sync() -> None:
    try:
        asyncio.run(_pool.close())
    except Exception as exc:
        logger.warning("Could not close browser pool synchronously: %s", exc)


atexit.register(_close_browser_pool_sync)


async def fetch_url(
    url: str,
    *,
    domain: str,
    selector: str = "a",
    extract_links: bool = False,
    pattern: str = "",
    wait_for_selector: str = "",
    wait_seconds: int = 3,
    timeout_seconds: int = 30,
) -> BrowserFetchResult:
    """Fetch *url* using a real browser with persistent session reuse.

    Rate-limited per domain, stealth-launched, and returns classified results
    for login/challenge/bot/not-found/timeout outcomes.
    """
    store = BrowserSessionStore()
    metadata = store.load_metadata(domain)
    await _rate_limit_sleep(metadata)

    try:
        await assert_url_safe(url)
    except SSRFBlockedError as exc:
        return BrowserFetchResult(
            ok=False,
            category=ToolResultCategory.BLOCKED,
            text=_format_failure_message(
                ToolResultCategory.BLOCKED, f"SSRF blocked: {exc}"
            ),
            final_url="",
            title="",
        )

    if metadata is not None and metadata.requires_headed:
        return BrowserFetchResult(
            ok=False,
            category=ToolResultCategory.BLOCKED,
            text=_format_failure_message(
                ToolResultCategory.BLOCKED,
                f"[BLOCKED - HEADED_LOGIN_REQUIRED] {domain} is flagged as requiring a "
                f"headed browser. Log in via the Browser Stream UI for {domain}, then retry.",
            ),
            final_url="",
            title="",
        )

    storage_state = _load_session(store, domain)

    page: Any | None = None
    context: Any | None = None

    try:
        context = await _pool.new_context(storage_state)
        page = await context.new_page()
        await apply_stealth_async(page)

        response = await page.goto(
            url,
            timeout=timeout_seconds * 1000,
            wait_until="domcontentloaded",
        )

        if wait_for_selector:
            await page.wait_for_selector(
                wait_for_selector, timeout=timeout_seconds * 1000
            )
        else:
            await page.wait_for_timeout(wait_seconds * 1000)

        final_url = page.url
        title = await page.title()

        if response is not None and response.status == 404:
            return BrowserFetchResult(
                ok=False,
                category=ToolResultCategory.NOT_FOUND,
                text=_format_failure_message(
                    ToolResultCategory.NOT_FOUND,
                    f"[NOT FOUND] {url} returned 404.",
                ),
                final_url=final_url,
                title=title,
            )

        is_blocked, category, failure_text = _classify_page(final_url, title, "")
        if is_blocked:
            return BrowserFetchResult(
                ok=False,
                category=category,
                text=failure_text,
                final_url=final_url,
                title=title,
            )

        text = await _extract_text(page)

        is_blocked, category, failure_text = _classify_page(final_url, title, text)
        if is_blocked:
            return BrowserFetchResult(
                ok=False,
                category=category,
                text=failure_text,
                final_url=final_url,
                title=title,
            )

        links: list[dict[str, Any]] = []
        if extract_links:
            links = await _extract_links(page, selector, pattern)

        # Persist refreshed session state so subsequent calls stay authenticated.
        try:
            refreshed_storage = cast(dict[str, Any], await context.storage_state())
            store.save_storage(domain, refreshed_storage)
            refreshed_cookies = cast(list[dict[str, Any]], await context.cookies())
            store.save_cookies(domain, refreshed_cookies)
        except Exception as exc:
            logger.warning("Failed to persist session for %s: %s", domain, exc)

        return BrowserFetchResult(
            ok=True,
            category=ToolResultCategory.SUCCESS,
            text=text,
            links=links,
            final_url=final_url,
            title=title,
        )

    except Exception as exc:
        logger.warning("browser_fetch partial failure for %s: %s", url, exc)
        category = (
            ToolResultCategory.TIMEOUT
            if "timeout" in str(exc).lower()
            else ToolResultCategory.TRANSIENT_OTHER
        )
        error_text = _format_failure_message(
            category,
            f"Timeout fetching {url}: {exc}",
        )
        if "timeout" not in str(exc).lower():
            error_text = _format_failure_message(
                category,
                f"Error fetching {url}: {exc}",
            )
        return BrowserFetchResult(
            ok=False,
            category=category,
            text=error_text,
            final_url=page.url if page else "",
            title="",
        )

    finally:
        try:
            store.update_metadata(domain, last_used=datetime.now(UTC))
        except Exception as exc:
            logger.warning("Failed to update metadata for %s: %s", domain, exc)
        if context is not None:
            await _pool.close_context(context)
