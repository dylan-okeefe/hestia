"""Tests for the read_clipboard tool."""

import sys
from unittest.mock import AsyncMock, patch

import pytest

from hestia.tools.builtin.read_clipboard import read_clipboard


@pytest.mark.asyncio
async def test_read_clipboard_uses_first_successful_provider() -> None:
    with patch("hestia.tools.builtin.read_clipboard._run", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = [None, "clipboard content"]
        with patch("shutil.which", return_value="/usr/bin/xclip"):
            result = await read_clipboard()
    assert result == "clipboard content"
    assert mock_run.call_count >= 1


@pytest.mark.asyncio
async def test_read_clipboard_returns_empty_when_blank() -> None:
    with patch("hestia.tools.builtin.read_clipboard._run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = "   "
        with patch("shutil.which", return_value="/usr/bin/xclip"):
            result = await read_clipboard()
    assert result == ""


@pytest.mark.asyncio
async def test_read_clipboard_reports_no_provider() -> None:
    with patch("hestia.tools.builtin.read_clipboard._run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = None
        with patch.object(sys, "platform", "linux"), patch("shutil.which", return_value=None):
            result = await read_clipboard()
    assert "No clipboard provider found" in result
