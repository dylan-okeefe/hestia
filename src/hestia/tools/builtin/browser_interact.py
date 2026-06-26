"""Interact with JavaScript-driven pages (fill forms, click buttons, etc.)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from hestia.tools.browser.session_store import BrowserSessionStore, normalize_domain
from hestia.tools.browser.stealth import (
    STEALTH_LAUNCH_ARGS,
    apply_stealth_async,
    stealth_context_kwargs,
)
from hestia.tools.capabilities import NETWORK_EGRESS
from hestia.tools.metadata import tool

logger = logging.getLogger(__name__)


def _format_actions(actions: list[dict[str, Any]]) -> str:
    """Return a concise string representation of actions for error messages."""
    parts = []
    for action in actions:
        t = action.get("type", "unknown")
        selector = action.get("selector", "")
        value = action.get("value", "")
        if selector and value:
            parts.append(f"{t}({selector}={value!r})")
        elif selector:
            parts.append(f"{t}({selector})")
        else:
            parts.append(t)
    return " -> ".join(parts)


async def _run_interaction(
    url: str,
    *,
    domain: str,
    actions: list[dict[str, Any]],
    headless: bool = False,
    wait_seconds: int = 3,
    timeout_seconds: int = 30,
    return_html: bool = False,
) -> str:
    """Launch a browser, perform actions, and return page text or HTML."""
    from playwright.async_api import async_playwright

    store = BrowserSessionStore()
    storage_state = store.load_storage(domain)
    if storage_state is None:
        cookies = store.load_cookies(domain)
        if cookies:
            storage_state = {"cookies": cookies, "origins": []}

    browser = None
    context = None
    playwright_inst = None

    try:
        playwright_inst = await async_playwright().start()
        browser = await playwright_inst.chromium.launch(
            headless=headless,
            args=STEALTH_LAUNCH_ARGS,
        )
        context = await browser.new_context(**stealth_context_kwargs(storage_state))
        page = await context.new_page()
        await apply_stealth_async(page)

        await page.goto(url, timeout=timeout_seconds * 1000, wait_until="domcontentloaded")

        for idx, action in enumerate(actions):
            action_type = action.get("type", "").lower()
            selector = action.get("selector", "")
            value = action.get("value", "")
            action_timeout = action.get("timeout", timeout_seconds) * 1000

            if action_type == "fill":
                if not selector:
                    raise ValueError(f"Action {idx}: 'fill' requires a selector")
                await page.locator(selector).fill(str(value), timeout=action_timeout)
                if action.get("press_enter"):
                    await page.locator(selector).press("Enter")
                elif action.get("press_tab"):
                    await page.locator(selector).press("Tab")

            elif action_type == "click":
                if not selector:
                    raise ValueError(f"Action {idx}: 'click' requires a selector")
                await page.locator(selector).click(timeout=action_timeout)

            elif action_type == "select":
                if not selector:
                    raise ValueError(f"Action {idx}: 'select' requires a selector")
                await page.locator(selector).select_option(value, timeout=action_timeout)

            elif action_type == "wait":
                if not selector:
                    raise ValueError(f"Action {idx}: 'wait' requires a selector")
                await page.locator(selector).wait_for(timeout=action_timeout)

            elif action_type == "wait_for_navigation":
                await page.wait_for_load_state("networkidle", timeout=action_timeout)

            elif action_type == "wait_seconds":
                seconds = float(value) if value else action.get("seconds", wait_seconds)
                await page.wait_for_timeout(int(seconds * 1000))

            else:
                raise ValueError(f"Action {idx}: unknown action type {action_type!r}")

        if wait_seconds > 0:
            await page.wait_for_timeout(wait_seconds * 1000)

        result = await page.content() if return_html else await page.evaluate(
            "() => document.body.innerText || ''"
        )

        # Persist refreshed session state
        try:
            refreshed_storage = await context.storage_state()
            store.save_storage(domain, refreshed_storage)
            refreshed_cookies = await context.cookies()
            store.save_cookies(domain, refreshed_cookies)
        except Exception as exc:
            logger.warning("Failed to persist session for %s: %s", domain, exc)

        return str(result)

    finally:
        if context is not None:
            try:
                await context.close()
            except Exception as exc:
                logger.warning("Error closing context: %s", exc)
        if browser is not None:
            try:
                await browser.close()
            except Exception as exc:
                logger.warning("Error closing browser: %s", exc)
        if playwright_inst is not None:
            try:
                await playwright_inst.stop()
            except Exception as exc:
                logger.warning("Error stopping playwright: %s", exc)


@tool(
    name="browser_interact",
    public_description=(
        "Open a web page in a real browser and interact with it (fill forms, "
        "click buttons, select options, wait for elements). Use this for "
        "JavaScript-heavy sites where the data only appears after user interaction, "
        "such as search forms that don't work via URL parameters. "
        "Params: url (str), actions (list of dicts), headless (bool, default false), "
        "wait_seconds (int, default 3), timeout_seconds (int, default 30), "
        "return_html (bool, default false)."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Full URL to open."},
            "actions": {
                "type": "array",
                "description": (
                    "List of interaction steps. Each step is a dict with 'type' "
                    "(fill, click, select, wait, wait_for_navigation, wait_seconds), "
                    "'selector' (CSS selector), and 'value' (string). For 'fill', "
                    "set 'press_enter': true to submit after typing."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "selector": {"type": "string"},
                        "value": {"type": "string"},
                        "press_enter": {"type": "boolean"},
                        "press_tab": {"type": "boolean"},
                        "seconds": {"type": "number"},
                        "timeout": {"type": "integer"},
                    },
                },
            },
            "headless": {
                "type": "boolean",
                "description": "Run headless (default false). Set false for sites that block headless browsers.",
            },
            "wait_seconds": {
                "type": "integer",
                "description": "Extra seconds to wait after actions before extracting content.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Default timeout for page load and actions in seconds.",
            },
            "return_html": {
                "type": "boolean",
                "description": "Return raw HTML instead of visible text.",
            },
        },
        "required": ["url", "actions"],
    },
    max_inline_chars=6000,
    tags=["network", "browser", "builtin"],
    capabilities=[NETWORK_EGRESS],
)
async def browser_interact(
    url: str,
    actions: list[dict[str, Any]],
    headless: bool = False,
    wait_seconds: int = 3,
    timeout_seconds: int = 30,
    return_html: bool = False,
) -> str:
    """Open a page, perform actions, and return the resulting content."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        return f"Invalid URL: {url}"

    if not actions:
        return "No actions provided. Use browser_get for simple page fetches."

    domain = normalize_domain(parsed.hostname)

    try:
        return await _run_interaction(
            url,
            domain=domain,
            actions=actions,
            headless=headless,
            wait_seconds=wait_seconds,
            timeout_seconds=timeout_seconds,
            return_html=return_html,
        )
    except Exception as exc:
        logger.warning(
            "browser_interact failed for %s with actions %s: %s",
            url,
            _format_actions(actions),
            exc,
        )
        return f"Interaction failed: {exc}"
