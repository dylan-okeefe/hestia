"""Tests for http_get curl_cffi parameter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from hestia.tools.builtin.http_get import http_get, make_http_get_tool


@pytest.mark.asyncio
async def test_factory_http_get_accepts_use_curl_cffi() -> None:
    """The app-registered http_get (created by the factory) must expose use_curl_cffi."""
    tool_fn = make_http_get_tool(use_curl_cffi_fallback=False)
    with (
        patch(
            "hestia.tools.builtin.http_get._fetch_with_curl_cffi",
            new_callable=AsyncMock,
        ) as mock_curl,
        patch(
            "hestia.tools.builtin.http_get._CURL_CFFI_AVAILABLE",
            True,
        ),
    ):
        mock_curl.return_value = "curl_cffi body"
        result = await tool_fn(
            "https://example.com", timeout_seconds=10, use_curl_cffi=True
        )

    assert result == "curl_cffi body"
    mock_curl.assert_awaited_once_with(
        "https://example.com", 10, egress_audit_enabled=True
    )


@pytest.mark.asyncio
async def test_use_curl_cffi_invokes_curl_cffi_path() -> None:
    """When use_curl_cffi=True, the curl_cffi fetch path is used."""
    with (
        patch(
            "hestia.tools.builtin.http_get._fetch_with_curl_cffi",
            new_callable=AsyncMock,
        ) as mock_curl,
        patch(
            "hestia.tools.builtin.http_get._CURL_CFFI_AVAILABLE",
            True,
        ),
    ):
        mock_curl.return_value = "curl_cffi body"
        result = await http_get(
            "https://example.com", timeout_seconds=10, use_curl_cffi=True
        )

    assert result == "curl_cffi body"
    mock_curl.assert_awaited_once_with(
        "https://example.com", 10, egress_audit_enabled=True
    )


@pytest.mark.asyncio
async def test_use_curl_cffi_false_uses_httpx() -> None:
    """When use_curl_cffi=False, the normal httpx path is used."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "httpx body"
    mock_response.url = "https://example.com"
    mock_response.content = b"httpx body"
    mock_response.raise_for_status = MagicMock()

    with patch(
        "hestia.tools.builtin.http_get._fetch_with_httpx",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as mock_httpx:
        result = await http_get(
            "https://example.com", timeout_seconds=10, use_curl_cffi=False
        )

    assert result == "httpx body"
    mock_httpx.assert_awaited_once_with("https://example.com", 10)


@pytest.mark.asyncio
async def test_use_curl_cffi_false_403_does_not_fallback() -> None:
    """A 403 with use_curl_cffi=False does not invoke curl_cffi fallback."""
    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.text = "forbidden"
    mock_response.url = "https://example.com"
    mock_response.content = b"forbidden"
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "403", request=MagicMock(), response=mock_response
        )
    )

    with (
        patch(
            "hestia.tools.builtin.http_get._fetch_with_httpx",
            new_callable=AsyncMock,
            return_value=mock_response,
        ),
        patch(
            "hestia.tools.builtin.http_get._fetch_with_curl_cffi",
            new_callable=AsyncMock,
        ) as mock_curl,
        patch(
            "hestia.tools.builtin.http_get._CURL_CFFI_AVAILABLE",
            True,
        ),
        pytest.raises(httpx.HTTPStatusError),
    ):
        await http_get(
            "https://example.com", timeout_seconds=10, use_curl_cffi=False
        )

    mock_curl.assert_not_awaited()
