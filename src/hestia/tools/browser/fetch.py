"""Shared authenticated browser fetch helper."""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from playwright.async_api import async_playwright

from hestia.tools.browser.session_store import BrowserSessionStore
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
    return 3.0


async def _rate_limit_sleep(store: BrowserSessionStore, domain: str) -> None:
    """Sleep if the last fetch for *domain* was too recent."""
    metadata = store.load_metadata(domain)
    if metadata is None or metadata.last_used is None:
        return

    elapsed = (datetime.now(UTC) - metadata.last_used).total_seconds()
    min_delay = _get_min_delay_seconds()
    sleep_seconds = min_delay - elapsed + random.uniform(0.0, 0.5)
    if sleep_seconds > 0:
        logger.debug(
            "Rate-limiting fetch for %s (elapsed %.2fs, min_delay %.2fs, sleep %.2fs)",
            domain,
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


def _classify_page(url: str, title: str, text: str) -> tuple[bool, ToolResultCategory, str]:
    """Detect login/bot/not-found pages and return a failure description.

    Returns ``(is_blocked, category, message)``.
    """
    lower_url = url.lower()
    lower_title = title.lower()
    lower_text = text.lower()

    if any(path in lower_url for path in _LOGIN_PATHS):
        return (
            True,
            ToolResultCategory.BLOCKED,
            f"[BLOCKED - LOGIN_REQUIRED] Fetched {url} redirected to login page "
            f"({url}). Re-authenticate with browser_login.",
        )

    if any(phrase in lower_title for phrase in _LOGIN_PHRASES) or any(
        phrase in lower_text for phrase in _LOGIN_PHRASES
    ):
        return (
            True,
            ToolResultCategory.BLOCKED,
            f"[BLOCKED - LOGIN_REQUIRED] Fetched {url} presented a login or "
            f"challenge page ({url}). Re-authenticate with browser_login.",
        )

    if any(phrase in lower_text for phrase in _BOT_PHRASES):
        return (
            True,
            ToolResultCategory.BLOCKED,
            f"[BLOCKED] Bot protection page for {url} ({url}). "
            "The site is blocking automated access.",
        )

    if "404" in lower_text or any(phrase in lower_text for phrase in _NOT_FOUND_PHRASES[1:]):
        return (
            True,
            ToolResultCategory.NOT_FOUND,
            f"[NOT FOUND] {url} returned 404 or page not found.",
        )

    return False, ToolResultCategory.SUCCESS, ""


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
    await _rate_limit_sleep(store, domain)

    storage_state = _load_session(store, domain)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=STEALTH_LAUNCH_ARGS,
        )
        context = await browser.new_context(**stealth_context_kwargs(storage_state))
        page = await context.new_page()
        await apply_stealth_async(page)

        try:
            response = await page.goto(
                url,
                timeout=timeout_seconds * 1000,
                wait_until="networkidle",
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
                    text=f"[NOT FOUND] {url} returned 404.",
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
                refreshed_storage = await context.storage_state()
                store.save_storage(domain, refreshed_storage)
                refreshed_cookies = await context.cookies()
                store.save_cookies(domain, refreshed_cookies)
            except Exception as exc:
                logger.warning("Failed to persist session for %s: %s", domain, exc)

            store.update_metadata(domain, last_used=datetime.now(UTC))

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
            error_text = f"Timeout fetching {url}: {exc}"
            if "timeout" not in str(exc).lower():
                error_text = f"Error fetching {url}: {exc}"
            return BrowserFetchResult(
                ok=False,
                category=ToolResultCategory.TIMEOUT
                if "timeout" in str(exc).lower()
                else ToolResultCategory.TRANSIENT_OTHER,
                text=error_text,
                final_url=page.url if page else "",
                title="",
            )

        finally:
            await context.close()
            await browser.close()
