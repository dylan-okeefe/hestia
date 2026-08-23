"""Shared anti-detection (stealth) configuration for Playwright browsers.

Uses playwright-stealth (a port of puppeteer-extra-plugin-stealth) for
comprehensive runtime fingerprint evasion, layered on top of sensible launch
args and context defaults.
"""

from __future__ import annotations

from typing import Any

from playwright_stealth import Stealth

STEALTH_VIEWPORT = {"width": 1920, "height": 1080}

STEALTH_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)

STEALTH_LAUNCH_ARGS: list[str] = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--no-sandbox",
]

# Pre-configured Stealth instance matching our environment.
# chrome_runtime is left at its default (False) because enabling it can break
# some sites; the other evasions cover the common detection vectors.
_DEFAULT_STEALTH = Stealth(
    navigator_languages_override=("en-US", "en"),
    navigator_platform_override="Linux x86_64",
    navigator_user_agent_override=STEALTH_USER_AGENT,
    navigator_vendor_override="Google Inc.",
    webgl_vendor_override="Google Inc. (NVIDIA)",
    webgl_renderer_override="NVIDIA GeForce GTX 1660/PCIe/SSE2",
)


async def apply_stealth_async(context_or_page: Any) -> None:
    """Apply all stealth evasions to a Playwright BrowserContext or Page."""
    await _DEFAULT_STEALTH.apply_stealth_async(context_or_page)


def stealth_context_kwargs(storage_state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return kwargs for ``browser.new_context()`` with stealth settings applied.

    Pass the returned dict directly to ``browser.new_context(**kwargs)``.
    If *storage_state* is provided it is merged in.

    Note: the actual JS evasions are applied via ``apply_stealth_async()``
    after the context/page is created, not through these kwargs.
    """
    kwargs: dict[str, Any] = {
        "viewport": STEALTH_VIEWPORT,
        "user_agent": STEALTH_USER_AGENT,
        "locale": "en-US",
        "timezone_id": "America/New_York",
    }
    if storage_state is not None:
        kwargs["storage_state"] = storage_state
    return kwargs
