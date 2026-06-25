"""Extract embedded JSON variables from web pages using a real browser."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

from hestia.tools.browser.session_store import BrowserSessionStore, normalize_domain
from hestia.tools.browser.stealth import (
    STEALTH_LAUNCH_ARGS,
    apply_stealth_async,
    stealth_context_kwargs,
)
from hestia.tools.capabilities import NETWORK_EGRESS, READ_LOCAL
from hestia.tools.metadata import tool

logger = logging.getLogger(__name__)


def _parse_variable_name(variable: str) -> tuple[str, list[str] | None]:
    """Parse a variable expression like window.foo.bar['baz'] into parts.

    Returns the root variable name and optional bracket/key path.
    """
    # Normalize whitespace
    expr = variable.strip()
    # Strip leading window. if present
    if expr.startswith("window."):
        expr = expr[7:]

    # Split by dots and bracket notation
    parts: list[str] = []
    current = ""
    i = 0
    in_brackets = False
    bracket_content = ""
    while i < len(expr):
        ch = expr[i]
        if ch == "[":
            if current:
                parts.append(current)
                current = ""
            in_brackets = True
            bracket_content = ""
        elif ch == "]" and in_brackets:
            in_brackets = False
            # Remove surrounding quotes
            bracket_content = bracket_content.strip().strip('"').strip("'")
            parts.append(bracket_content)
        elif in_brackets:
            bracket_content += ch
        elif ch == ".":
            if current:
                parts.append(current)
                current = ""
        else:
            current += ch
        i += 1
    if current:
        parts.append(current)

    if not parts:
        raise ValueError(f"Invalid variable expression: {variable!r}")

    return parts[0], parts[1:] if len(parts) > 1 else None


def _parse_access_chain(chain: str) -> list[str]:
    """Parse a dot/bracket access chain into a list of keys.

    Example: '.providerData["mosaic-provider-jobcards"]' ->
    ['providerData', 'mosaic-provider-jobcards'].
    """
    keys: list[str] = []
    i = 0
    current = ""
    in_brackets = False
    while i < len(chain):
        ch = chain[i]
        if ch == ".":
            if current:
                keys.append(current)
                current = ""
        elif ch == "[":
            if current:
                keys.append(current)
                current = ""
            in_brackets = True
        elif ch == "]" and in_brackets:
            in_brackets = False
            keys.append(current.strip().strip('"').strip("'"))
            current = ""
        else:
            current += ch
        i += 1
    if current:
        keys.append(current)
    return keys


def _extract_variable(html: str, root_name: str) -> Any | None:
    """Find the first assignment of *root_name* in <script> tags and parse it.

    If the assignment includes dot/bracket access after the root name (e.g.
    ``window.mosaic.providerData["key"] = {...}``), the parsed value is wrapped
    back into the implied object structure so callers can navigate it with the
    full variable path.
    """
    script_pattern = re.compile(r"<script[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)
    assignment_re = re.compile(
        rf"(?:window\.)?{re.escape(root_name)}"
        rf"((?:\s*\.\s*[a-zA-Z_$][a-zA-Z0-9_$]*|\s*\[[^\]]+\])*)"
        rf"\s*=\s*(\{{.*?\}})\s*;",
        re.DOTALL,
    )
    for script_match in script_pattern.finditer(html):
        script = script_match.group(1)
        for m in assignment_re.finditer(script):
            chain_str = m.group(1)
            value_str = m.group(2)
            try:
                value = json.loads(value_str)
            except json.JSONDecodeError as exc:
                logger.debug("JSON parse failed for %s: %s", root_name, exc)
                continue
            keys = _parse_access_chain(chain_str)
            for key in reversed(keys):
                value = {key: value}
            return value
    return None


def _get_path(data: Any, path: str) -> Any:
    """Navigate a dot-separated path through nested dicts/lists.

    Supports integer indices for list access.
    """
    if not path:
        return data
    parts = path.split(".")
    current: Any = data
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if current is None:
            raise KeyError(f"Cannot navigate path {path!r}: encountered None")
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(f"Key {part!r} not found in path {path!r}")
            current = current[part]
        elif isinstance(current, list):
            try:
                idx = int(part)
            except ValueError as exc:
                raise KeyError(
                    f"Expected integer index for list in path {path!r}, got {part!r}"
                ) from exc
            if idx < 0 or idx >= len(current):
                raise IndexError(f"Index {idx} out of range in path {path!r}")
            current = current[idx]
        else:
            raise KeyError(f"Cannot navigate into {type(current).__name__} at {part!r}")
    return current


async def _fetch_page_html(
    url: str,
    *,
    domain: str,
    headless: bool = True,
    wait_seconds: int = 3,
    timeout_seconds: int = 30,
) -> str:
    """Load *url* in a browser and return the raw HTML."""
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
        if wait_seconds > 0:
            await page.wait_for_timeout(wait_seconds * 1000)

        html = await page.content()

        # Persist refreshed session state
        try:
            refreshed_storage = await context.storage_state()
            store.save_storage(domain, refreshed_storage)
            refreshed_cookies = await context.cookies()
            store.save_cookies(domain, refreshed_cookies)
        except Exception as exc:
            logger.warning("Failed to persist session for %s: %s", domain, exc)

        return html

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
    name="browser_get_json",
    public_description=(
        "Fetch a web page with a real browser and extract an embedded JSON variable. "
        "Use this for JavaScript-heavy sites that store their data in window.* "
        "variables, such as Indeed (window.mosaic.providerData, window._initialData). "
        "Params: url (str), variable (str) — e.g. 'window.mosaic.providerData[\"mosaic-provider-jobcards\"]' "
        "or '_initialData', json_path (str, optional) — dot-separated path into the JSON object, "
        "headless (bool, default true), wait_seconds (int, default 3), timeout_seconds (int, default 30)."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Full URL to fetch."},
            "variable": {
                "type": "string",
                "description": (
                    "Embedded variable name, e.g. 'window.mosaic.providerData[\"mosaic-provider-jobcards\"]' "
                    "or '_initialData'."
                ),
            },
            "json_path": {
                "type": "string",
                "description": (
                    "Optional dot-separated path into the extracted JSON object "
                    "(e.g. 'metaData.mosaicProviderJobCardsModel.results')."
                ),
            },
            "headless": {
                "type": "boolean",
                "description": "Run headless (default true). Set false for sites that block headless browsers.",
            },
            "wait_seconds": {
                "type": "integer",
                "description": "Extra seconds to wait for JS hydration before extracting JSON.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Page load timeout in seconds.",
            },
        },
        "required": ["url", "variable"],
    },
    max_inline_chars=6000,
    tags=["network", "browser", "builtin"],
    capabilities=[NETWORK_EGRESS, READ_LOCAL],
)
async def browser_get_json(
    url: str,
    variable: str,
    json_path: str = "",
    headless: bool = True,
    wait_seconds: int = 3,
    timeout_seconds: int = 30,
) -> str:
    """Fetch a URL with a browser and extract embedded JSON data."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        return f"Invalid URL: {url}"

    domain = normalize_domain(parsed.hostname)

    try:
        html = await _fetch_page_html(
            url,
            domain=domain,
            headless=headless,
            wait_seconds=wait_seconds,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        logger.warning("browser_get_json failed to load %s: %s", url, exc)
        return f"Error loading page: {exc}"

    try:
        root_name, _ = _parse_variable_name(variable)
    except ValueError as exc:
        return f"Invalid variable expression: {exc}"

    data = _extract_variable(html, root_name)
    if data is None:
        return (
            f"Could not find embedded JSON variable {variable!r} in {url}. "
            "The page may load the data asynchronously or use a different variable name."
        )

    # If the user provided a full variable path with bracket/dotted access,
    # navigate through the extracted root object to reach the requested sub-object.
    _, key_path = _parse_variable_name(variable)
    try:
        if key_path:
            for key in key_path:
                if isinstance(data, dict) and key in data:
                    data = data[key]
                else:
                    return (
                        f"Variable {variable!r} found, but key {key!r} is missing "
                        f"in the extracted object."
                    )
        if json_path:
            data = _get_path(data, json_path)
    except (KeyError, IndexError, ValueError) as exc:
        return f"JSON path navigation failed: {exc}"

    try:
        return json.dumps(data, indent=2, ensure_ascii=False)
    except TypeError as exc:
        return f"Extracted data is not JSON-serializable: {exc}"
