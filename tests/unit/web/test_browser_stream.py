"""Unit tests for SessionStreamManager and browser stream WebSocket."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from hestia.tools.browser.session_store import BrowserSessionStore
from hestia.web.api import create_web_app
from hestia.web.browser_stream import SessionStreamManager
from hestia.web.context import WebContext, set_web_context


@pytest.fixture(autouse=True)
def _clear_web_context() -> None:
    """Clear the global web context before each test."""
    from hestia.web import context as ctx_mod

    ctx_mod._ctx = None


@pytest.fixture
def mock_store(tmp_path: pytest.TempPathFactory) -> BrowserSessionStore:
    return BrowserSessionStore(base_dir=tmp_path)


@pytest.fixture
def manager(mock_store: BrowserSessionStore) -> SessionStreamManager:
    return SessionStreamManager(store=mock_store)


def _make_mock_playwright() -> tuple[
    MagicMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock, MagicMock
]:
    """Build a full mock Playwright stack and return key objects."""
    mock_cdp = MagicMock()
    mock_cdp.send = AsyncMock()
    mock_cdp.on = MagicMock()

    mock_page = AsyncMock()
    mock_page.mouse = MagicMock()
    mock_page.mouse.click = AsyncMock()
    mock_page.mouse.move = AsyncMock()
    mock_page.mouse.wheel = AsyncMock()
    mock_page.keyboard = MagicMock()
    mock_page.keyboard.press = AsyncMock()
    mock_page.keyboard.type = AsyncMock()
    mock_page.context.new_cdp_session = AsyncMock(return_value=mock_cdp)

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.cookies = AsyncMock(return_value=[{"name": "s", "value": "v"}])
    mock_context.storage_state = AsyncMock(
        return_value={"cookies": [{"name": "s", "value": "v"}], "origins": []}
    )

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)

    mock_playwright = AsyncMock()
    mock_playwright.chromium = AsyncMock()
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_playwright.stop = AsyncMock()

    mock_cm = MagicMock()
    mock_cm.start = AsyncMock(return_value=mock_playwright)
    mock_cm.stop = AsyncMock()

    return mock_cm, mock_playwright, mock_browser, mock_context, mock_page, mock_cdp


def _inject_playwright_module(mock_cm: MagicMock) -> None:
    """Inject a mock playwright.async_api module into sys.modules."""
    mock_async_api = SimpleNamespace()
    mock_async_api.async_playwright = MagicMock(return_value=mock_cm)

    mock_playwright_pkg = SimpleNamespace()
    mock_playwright_pkg.async_api = mock_async_api

    sys.modules["playwright"] = mock_playwright_pkg
    sys.modules["playwright.async_api"] = mock_async_api


class TestStartSession:
    @pytest.mark.asyncio
    async def test_start_session_launches_browser_and_returns_id(
        self, manager: SessionStreamManager
    ) -> None:
        mock_cm, mock_playwright, mock_browser, mock_context, mock_page, mock_cdp = (
            _make_mock_playwright()
        )
        _inject_playwright_module(mock_cm)

        session_id = await manager.start("https://example.com/login")

        assert session_id is not None
        assert manager.is_active()
        assert manager.get_session_id() == session_id

        mock_playwright.chromium.launch.assert_called_once_with(headless=True)
        mock_browser.new_context.assert_awaited_once()
        mock_context.new_page.assert_awaited_once()
        mock_page.goto.assert_called_once_with(
            "https://example.com/login", wait_until="domcontentloaded"
        )
        mock_page.context.new_cdp_session.assert_called_once_with(mock_page)
        mock_cdp.send.assert_called_once_with(
            "Page.startScreencast",
            {
                "format": "jpeg",
                "quality": 80,
                "maxWidth": 1920,
                "maxHeight": 1080,
                "everyNthFrame": 1,
            },
        )

    @pytest.mark.asyncio
    async def test_start_session_raises_when_already_active(
        self, manager: SessionStreamManager
    ) -> None:
        mock_cm, *_ = _make_mock_playwright()
        _inject_playwright_module(mock_cm)

        await manager.start("https://example.com/login")
        with pytest.raises(RuntimeError, match="Session already active"):
            await manager.start("https://example.com/login")


class TestStopSession:
    @pytest.mark.asyncio
    async def test_stop_session_saves_cookies_and_closes(
        self, manager: SessionStreamManager, mock_store: BrowserSessionStore
    ) -> None:
        mock_cm, mock_playwright, mock_browser, mock_context, mock_page, mock_cdp = (
            _make_mock_playwright()
        )
        _inject_playwright_module(mock_cm)

        session_id = await manager.start("https://example.com/login")

        summary = await manager.stop(session_id)

        assert summary["domain"] == "example.com"
        assert summary["saved"] is True
        assert not manager.is_active()

        mock_cdp.send.assert_any_await("Page.stopScreencast")
        mock_playwright.stop.assert_awaited_once()
        mock_browser.close.assert_awaited_once()

        # Verify store received saved data
        assert mock_store.load_cookies("example.com") != []

    @pytest.mark.asyncio
    async def test_stop_raises_on_mismatched_session_id(
        self, manager: SessionStreamManager
    ) -> None:
        with pytest.raises(ValueError, match="Session not found or ID mismatch"):
            await manager.stop("nonexistent-id")


class TestForwardInput:
    @pytest.mark.asyncio
    async def test_forward_input_dispatches_click(
        self, manager: SessionStreamManager
    ) -> None:
        mock_cm, *_rest = _make_mock_playwright()
        mock_page = _rest[3]
        _inject_playwright_module(mock_cm)

        session_id = await manager.start("https://example.com/login")

        await manager.forward_input(
            session_id, {"type": "click", "x": 100, "y": 200}
        )
        mock_page.mouse.click.assert_called_once_with(100, 200)

    @pytest.mark.asyncio
    async def test_forward_input_dispatches_keydown(
        self, manager: SessionStreamManager
    ) -> None:
        mock_cm, *_rest = _make_mock_playwright()
        mock_page = _rest[3]
        _inject_playwright_module(mock_cm)

        session_id = await manager.start("https://example.com/login")

        await manager.forward_input(
            session_id, {"type": "keydown", "key": "Enter"}
        )
        mock_page.keyboard.press.assert_called_once_with("Enter")

    @pytest.mark.asyncio
    async def test_forward_input_dispatches_type(
        self, manager: SessionStreamManager
    ) -> None:
        mock_cm, *_rest = _make_mock_playwright()
        mock_page = _rest[3]
        _inject_playwright_module(mock_cm)

        session_id = await manager.start("https://example.com/login")

        await manager.forward_input(
            session_id, {"type": "type", "text": "hello"}
        )
        mock_page.keyboard.type.assert_called_once_with("hello")

    @pytest.mark.asyncio
    async def test_forward_input_dispatches_scroll(
        self, manager: SessionStreamManager
    ) -> None:
        mock_cm, *_rest = _make_mock_playwright()
        mock_page = _rest[3]
        _inject_playwright_module(mock_cm)

        session_id = await manager.start("https://example.com/login")

        await manager.forward_input(
            session_id,
            {"type": "scroll", "x": 100, "y": 200, "deltaX": 0, "deltaY": 100},
        )
        mock_page.mouse.move.assert_called_once_with(100, 200)
        mock_page.mouse.wheel.assert_called_once_with(0, 100)

    @pytest.mark.asyncio
    async def test_forward_input_validates_coordinates(
        self, manager: SessionStreamManager
    ) -> None:
        mock_cm, *_rest = _make_mock_playwright()
        mock_page = _rest[3]
        _inject_playwright_module(mock_cm)

        session_id = await manager.start("https://example.com/login")

        # Negative coordinates should be ignored
        await manager.forward_input(
            session_id, {"type": "click", "x": -1, "y": 100}
        )
        mock_page.mouse.click.assert_not_called()

        # Coordinates exceeding viewport should be ignored
        await manager.forward_input(
            session_id, {"type": "click", "x": 2000, "y": 100}
        )
        mock_page.mouse.click.assert_not_called()

        # Y out of bounds
        await manager.forward_input(
            session_id, {"type": "click", "x": 100, "y": 2000}
        )
        mock_page.mouse.click.assert_not_called()


class TestFrameDelivery:
    @pytest.mark.asyncio
    async def test_frame_delivery_to_connected_clients(
        self, manager: SessionStreamManager
    ) -> None:
        mock_cm, *_rest = _make_mock_playwright()
        mock_cdp = _rest[4]
        _inject_playwright_module(mock_cm)

        await manager.start("https://example.com/login")

        # Capture the frame handler registered on the CDP session
        assert mock_cdp.on.called
        handler = mock_cdp.on.call_args[0][1]

        mock_ws = AsyncMock()
        manager._session.ws_clients.add(mock_ws)

        jpeg_bytes = b"fake_jpeg_data"
        frame_params = {
            "data": base64.b64encode(jpeg_bytes).decode(),
            "sessionId": 42,
        }
        handler(frame_params)

        # Give the asyncio task a chance to run
        await asyncio.sleep(0.05)

        mock_ws.send_bytes.assert_called_once_with(jpeg_bytes)
        mock_cdp.send.assert_any_await(
            "Page.screencastFrameAck", {"sessionId": 42}
        )

    @pytest.mark.asyncio
    async def test_frame_delivery_removes_dead_clients(
        self, manager: SessionStreamManager
    ) -> None:
        mock_cm, *_rest = _make_mock_playwright()
        mock_cdp = _rest[4]
        _inject_playwright_module(mock_cm)

        await manager.start("https://example.com/login")

        handler = mock_cdp.on.call_args[0][1]

        mock_ws = AsyncMock()
        mock_ws.send_bytes = AsyncMock(side_effect=RuntimeError("disconnected"))
        manager._session.ws_clients.add(mock_ws)

        frame_params = {
            "data": base64.b64encode(b"data").decode(),
            "sessionId": 1,
        }
        handler(frame_params)
        await asyncio.sleep(0.05)

        assert mock_ws not in manager._session.ws_clients


class TestWebSocketEndpoint:
    @pytest.fixture
    def client(self, manager: SessionStreamManager) -> TestClient:
        auth_manager = MagicMock()
        auth_manager.validate_token = MagicMock(return_value=("valid", MagicMock()))

        mock_app = MagicMock()
        mock_app.config = MagicMock()

        ctx = WebContext(
            session_store=AsyncMock(),
            proposal_store=AsyncMock(),
            style_store=AsyncMock(),
            scheduler_store=AsyncMock(),
            trace_store=AsyncMock(),
            failure_store=AsyncMock(),
            workflow_store=AsyncMock(),
            execution_store=AsyncMock(),
            error_resolution_store=AsyncMock(),
            app=mock_app,
            auth_manager=auth_manager,
            user_store=AsyncMock(),
            browser_session_store=manager._store,
            stream_manager=manager,
        )
        set_web_context(ctx)
        app = create_web_app()
        return TestClient(app)

    @pytest.mark.asyncio
    async def test_ws_endpoint_rejects_invalid_session(
        self, client: TestClient, manager: SessionStreamManager
    ) -> None:
        mock_cm, *_ = _make_mock_playwright()
        _inject_playwright_module(mock_cm)
        await manager.start("https://example.com/login")

        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect(
                "/api/browser-session/stream/wrong-id",
                headers={"Authorization": "Bearer valid_token"},
            ) as ws,
        ):
            ws.receive_text()

        assert exc_info.value.code == 4004

    @pytest.mark.asyncio
    async def test_ws_endpoint_accepts_valid_auth_header(
        self, client: TestClient, manager: SessionStreamManager
    ) -> None:
        mock_cm, *_rest = _make_mock_playwright()
        mock_page = _rest[3]
        _inject_playwright_module(mock_cm)
        session_id = await manager.start("https://example.com/login")

        with client.websocket_connect(
            f"/api/browser-session/stream/{session_id}",
            headers={"Authorization": "Bearer valid_token"},
        ) as ws:
            ws.send_text(
                json.dumps({"type": "click", "x": 100, "y": 200})
            )

        mock_page.mouse.click.assert_called_once_with(100, 200)

    @pytest.mark.asyncio
    async def test_ws_endpoint_rejects_missing_auth(
        self, client: TestClient, manager: SessionStreamManager
    ) -> None:
        mock_cm, *_ = _make_mock_playwright()
        _inject_playwright_module(mock_cm)
        session_id = await manager.start("https://example.com/login")

        # Patch auth manager to reject tokens
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.auth_manager.validate_token = MagicMock(return_value=("missing", None))

        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect(
                f"/api/browser-session/stream/{session_id}",
            ),
        ):
            pass

        assert exc_info.value.code == 1008

    @pytest.mark.asyncio
    async def test_ws_endpoint_accepts_token_via_query_param(
        self, client: TestClient, manager: SessionStreamManager
    ) -> None:
        mock_cm, *_rest = _make_mock_playwright()
        mock_page = _rest[3]
        _inject_playwright_module(mock_cm)
        session_id = await manager.start("https://example.com/login")

        with client.websocket_connect(
            f"/api/browser-session/stream/{session_id}?token=valid_token",
        ) as ws:
            ws.send_text(
                json.dumps({"type": "click", "x": 50, "y": 50})
            )

        mock_page.mouse.click.assert_called_once_with(50, 50)


class TestAutoTimeout:
    @pytest.mark.asyncio
    async def test_auto_timeout_stops_session(
        self, manager: SessionStreamManager
    ) -> None:
        mock_cm, *_rest = _make_mock_playwright()
        mock_cdp = _rest[4]
        _inject_playwright_module(mock_cm)
        session_id = await manager.start("https://example.com/login")

        # Patch the timeout to be very short
        manager._timeout_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await manager._timeout_task

        manager._timeout_task = asyncio.create_task(
            manager._auto_stop(session_id)
        )

        # Override sleep to be immediate
        original_sleep = asyncio.sleep

        async def _immediate_sleep(_delay: float) -> None:
            await original_sleep(0)

        with patch("hestia.web.browser_stream.asyncio.sleep", _immediate_sleep):
            # Wait for the auto-stop task to complete
            if manager._timeout_task is not None:
                await manager._timeout_task

        assert not manager.is_active()
        mock_cdp.send.assert_any_await("Page.stopScreencast")
