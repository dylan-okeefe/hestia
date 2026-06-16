"""Browser session streaming manager using Playwright CDP screencast."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from fastapi import WebSocket

from hestia.security.ssrf import SSRFBlockedError, assert_url_safe
from hestia.tools.browser.session_store import BrowserSessionStore, normalize_domain
from hestia.tools.browser.stealth import (
    STEALTH_LAUNCH_ARGS,
    apply_stealth_async,
    stealth_context_kwargs,
)

logger = logging.getLogger(__name__)

_VIEWPORT = {"width": 1920, "height": 1080}
_TIMEOUT_SECONDS = 600  # 10 minutes


@dataclass
class _StreamSession:
    session_id: str
    domain: str
    page: Any  # Playwright Page
    browser: Any  # Playwright Browser
    playwright: Any  # Playwright instance
    context: Any  # Playwright BrowserContext
    started_at: datetime
    cdp_session: Any  # Playwright CDPSession
    ws_clients: set[WebSocket] = field(default_factory=set)


class SessionStreamManager:
    """Manages exactly one active headless Chromium instance with CDP screencast."""

    def __init__(self, store: BrowserSessionStore) -> None:
        self._store = store
        self._session: _StreamSession | None = None
        self._lock = asyncio.Lock()
        self._timeout_task: asyncio.Task[Any] | None = None

    def is_active(self) -> bool:
        """Return True if a session is currently running."""
        return self._session is not None

    def get_session_id(self) -> str | None:
        """Return the active session ID, or None."""
        return self._session.session_id if self._session is not None else None

    async def start(self, url: str, headed: bool = False) -> str:
        """Launch browser, navigate to URL, start screencast. Returns session_id.

        Args:
            url: The URL to navigate to.
            headed: If True, launch a visible browser window (headless=False).
                This evades bot detection on sites that block headless browsers
                while still streaming the screen via CDP screencast.
        """
        async with self._lock:
            if self._session is not None:
                raise RuntimeError("Session already active")

            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"
            parsed = urlparse(url)
            domain = normalize_domain(parsed.hostname or "")
            if not domain:
                raise ValueError(f"Invalid URL: {url}")

            try:
                await assert_url_safe(url)
            except SSRFBlockedError as exc:
                raise SSRFBlockedError(f"SSRF blocked: {exc}") from exc

            session_id = str(uuid.uuid4())
            playwright = None
            browser = None
            context = None
            page = None

            try:
                from playwright.async_api import async_playwright

                playwright = await async_playwright().start()
                browser = await playwright.chromium.launch(
                    headless=not headed,
                    args=STEALTH_LAUNCH_ARGS,
                )

                storage_state = self._store.load_storage(domain)
                if storage_state is None:
                    cookies = self._store.load_cookies(domain)
                    if cookies:
                        storage_state = {"cookies": cookies, "origins": []}

                context = await browser.new_context(
                    **stealth_context_kwargs(storage_state)
                )
                page = await context.new_page()
                await apply_stealth_async(page)
                await page.goto(url, wait_until="domcontentloaded")

                cdp_session = await page.context.new_cdp_session(page)
                await cdp_session.send(
                    "Page.startScreencast",
                    {
                        "format": "jpeg",
                        "quality": 80,
                        "maxWidth": 1920,
                        "maxHeight": 1080,
                        "everyNthFrame": 1,
                    },
                )

                session = _StreamSession(
                    session_id=session_id,
                    domain=domain,
                    page=page,
                    browser=browser,
                    playwright=playwright,
                    context=context,
                    started_at=datetime.now(UTC),
                    cdp_session=cdp_session,
                )

                def _on_frame(params: dict[str, Any]) -> None:
                    asyncio.create_task(self._handle_frame(session, params))

                cdp_session.on("Page.screencastFrame", _on_frame)

                self._session = session
                self._timeout_task = asyncio.create_task(
                    self._auto_stop(session_id)
                )
                return session_id
            except Exception:
                await self._cleanup(playwright, browser, context, page)
                raise

    async def _handle_frame(
        self, session: _StreamSession, params: dict[str, Any]
    ) -> None:
        """Decode and broadcast a screencast frame to all connected WebSockets."""
        data = params.get("data", "")
        frame_session_id = params.get("sessionId", 0)
        try:
            jpeg_bytes = base64.b64decode(data)
        except Exception:
            logger.exception("Failed to decode screencast frame")
            return

        if not session.ws_clients:
            logger.debug("No WS clients for session %s, skipping frame", session.session_id)
        else:
            logger.debug("Broadcasting frame to %d clients for session %s", len(session.ws_clients), session.session_id)

        disconnected: set[WebSocket] = set()
        for ws in list(session.ws_clients):
            try:
                await ws.send_bytes(jpeg_bytes)
            except Exception:
                disconnected.add(ws)

        if disconnected:
            session.ws_clients -= disconnected

        try:
            await session.cdp_session.send(
                "Page.screencastFrameAck", {"sessionId": frame_session_id}
            )
        except Exception:
            logger.exception("Failed to ack screencast frame")

    async def _auto_stop(self, session_id: str) -> None:
        """Auto-stop the session after timeout."""
        await asyncio.sleep(_TIMEOUT_SECONDS)
        if self._session is not None and self._session.session_id == session_id:
            logger.info("Browser stream session %s auto-timed out", session_id)
            try:
                await self.stop(session_id)
            except Exception:
                logger.exception("Auto-stop failed for session %s", session_id)

    async def stop(self, session_id: str) -> dict[str, Any]:
        """Stop screencast, save cookies/storage, close browser. Returns save summary."""
        async with self._lock:
            if self._session is None or self._session.session_id != session_id:
                raise ValueError("Session not found or ID mismatch")

            if self._timeout_task is not None:
                self._timeout_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._timeout_task
                self._timeout_task = None

            session = self._session

            try:
                await session.cdp_session.send("Page.stopScreencast")
            except Exception:
                logger.exception("Failed to stop screencast")

            cookies: list[dict[str, Any]] = []
            storage_state: dict[str, Any] | None = None
            try:
                cookies = await session.context.cookies()
                storage_state = await session.context.storage_state()
            except Exception:
                logger.exception("Failed to capture session state")

            if storage_state is not None:
                self._store.save_storage(session.domain, storage_state)
            if cookies:
                self._store.save_cookies(session.domain, cookies)

            self._store.update_metadata(session.domain, last_saved=datetime.now(UTC))

            await self._cleanup(
                session.playwright,
                session.browser,
                session.context,
                session.page,
            )

            self._session = None

            return {
                "domain": session.domain,
                "cookie_count": len(cookies),
                "saved": True,
            }

    async def _cleanup(
        self, playwright: Any, browser: Any, context: Any, page: Any
    ) -> None:
        """Close browser resources safely."""
        if page is not None:
            with contextlib.suppress(Exception):
                await page.close()
        if context is not None:
            with contextlib.suppress(Exception):
                await context.close()
        if browser is not None:
            with contextlib.suppress(Exception):
                await browser.close()
        if playwright is not None:
            with contextlib.suppress(Exception):
                await playwright.stop()

    async def forward_input(self, session_id: str, event: dict[str, Any]) -> None:
        """Dispatch mouse or keyboard event to the page."""
        if self._session is None or self._session.session_id != session_id:
            return

        session = self._session
        event_type = event.get("type")

        x = y = -1
        if event_type in ("click", "mousemove", "scroll"):
            x = event.get("x", -1)
            y = event.get("y", -1)
            if not (0 <= x <= 1920 and 0 <= y <= 1080):
                return

        try:
            if event_type == "click":
                await session.page.mouse.click(x, y)
                await self._broadcast_input_mode(session)
            elif event_type == "mousemove":
                await session.page.mouse.move(x, y)
            elif event_type == "keydown":
                key = event.get("key", "")
                if key:
                    await session.page.keyboard.press(key)
            elif event_type == "type":
                text = event.get("text", "")
                if text:
                    await session.page.keyboard.type(text)
            elif event_type == "scroll":
                delta_x = event.get("deltaX", 0)
                delta_y = event.get("deltaY", 0)
                await session.page.mouse.move(x, y)
                await session.page.mouse.wheel(delta_x, delta_y)
        except Exception:
            logger.exception("Failed to forward input event")

    async def _broadcast_input_mode(self, session: _StreamSession) -> None:
        """Check if the focused element is a password input and notify clients."""
        try:
            is_password = await session.page.evaluate(
                "() => document.activeElement && document.activeElement.type === 'password'"
            )
            mode = "password" if is_password else "text"
            msg = f'{{"type": "input_mode", "mode": "{mode}"}}'
            disconnected: set[WebSocket] = set()
            for ws in list(session.ws_clients):
                try:
                    await ws.send_text(msg)
                except Exception:
                    disconnected.add(ws)
            if disconnected:
                session.ws_clients -= disconnected
        except Exception:
            logger.exception("Failed to broadcast input mode")
