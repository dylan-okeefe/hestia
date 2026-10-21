"""L234 integration tests: real-ffmpeg photo → JPEG data URL transform.

These tests shell out to the real ffmpeg binary (a Hestia dependency, also
used by the voice pipeline) and assert the output dimensions, JPEG
decodability, and the ~400KB output cap.
"""

from __future__ import annotations

import base64
import shutil
import subprocess
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Message, PhotoSize, Update, User

from hestia.config import TelegramConfig
from hestia.core.vision import jpeg_dimensions
from hestia.platforms.telegram_adapter import _VISION_MAX_JPEG_BYTES, TelegramAdapter

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _generate_test_image(path: str, width: int, height: int) -> None:
    """Render a deterministic test image with ffmpeg's lavfi testsrc2."""
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi",
            "-i", f"testsrc2=size={width}x{height}:duration=0.1",
            "-frames:v", "1",
            path, "-y",
        ],
        check=True,
    )


@pytest.fixture
def big_image(tmp_path: Any) -> str:
    path = str(tmp_path / "big.jpg")
    _generate_test_image(path, 2000, 1200)
    return path


@pytest.fixture
def small_image(tmp_path: Any) -> str:
    path = str(tmp_path / "small.jpg")
    _generate_test_image(path, 100, 80)
    return path


@pytest.fixture
def adapter() -> TelegramAdapter:
    return TelegramAdapter(
        TelegramConfig(bot_token="test:token12345", vision=True, allowed_users=["12345"])
    )


def _decode(url: str) -> bytes:
    assert url.startswith("data:image/jpeg;base64,")
    return base64.b64decode(url.split(",", 1)[1])


@pytest.mark.asyncio
async def test_photo_to_jpeg_data_url_downscales_longest_side(
    adapter: TelegramAdapter, big_image: str
) -> None:
    """2000x1200 input → longest side capped at 1024, aspect preserved, decodable JPEG."""
    url = await adapter._photo_to_jpeg_data_url(big_image, max_edge=1024)
    blob = _decode(url)

    assert blob[:2] == b"\xff\xd8"  # JPEG SOI marker
    dims = jpeg_dimensions(url)
    assert dims is not None
    width, height = dims
    assert max(width, height) <= 1024
    assert width == 1024  # longest side hits the cap exactly
    assert height == 614  # 1200 * (1024/2000), aspect preserved
    assert len(blob) <= _VISION_MAX_JPEG_BYTES


@pytest.mark.asyncio
async def test_photo_to_jpeg_data_url_does_not_upscale(
    adapter: TelegramAdapter, small_image: str
) -> None:
    """A 100x80 input keeps its dimensions (no upscaling)."""
    url = await adapter._photo_to_jpeg_data_url(small_image, max_edge=1024)
    dims = jpeg_dimensions(url)
    assert dims == (100, 80)


@pytest.mark.asyncio
async def test_photo_to_jpeg_data_url_respects_custom_edge(
    adapter: TelegramAdapter, big_image: str
) -> None:
    """A smaller configured edge cap is honored (vision_max_edge_px wiring)."""
    url = await adapter._photo_to_jpeg_data_url(big_image, max_edge=768)
    dims = jpeg_dimensions(url)
    assert dims is not None
    assert max(dims) <= 768


@pytest.mark.asyncio
async def test_handle_photo_end_to_end_with_real_ffmpeg(
    adapter: TelegramAdapter, big_image: str
) -> None:
    """Full handler path: mock Telegram download (real bytes) → real ffmpeg → on_message."""
    mock_update = MagicMock(spec=Update)
    mock_user = MagicMock(spec=User)
    mock_user.id = 12345
    mock_user.username = "testuser"
    mock_update.effective_user = mock_user

    mock_message = MagicMock(spec=Message)
    mock_message.caption = "describe this chart"

    with open(big_image, "rb") as fh:
        payload = fh.read()

    mock_file = AsyncMock()

    def _download(path: str, **kwargs: Any) -> None:
        with open(path, "wb") as out:
            out.write(payload)

    mock_file.download_to_drive = AsyncMock(side_effect=_download)

    large = MagicMock(spec=PhotoSize)
    large.file_size = len(payload)
    large.get_file = AsyncMock(return_value=mock_file)
    small = MagicMock(spec=PhotoSize)
    small.file_size = 1000
    mock_message.photo = [small, large]
    mock_message.reply_text = AsyncMock()
    mock_update.effective_message = mock_message

    received: dict[str, Any] = {}

    async def on_message(
        platform: str,
        user: str,
        text: str,
        sender: str | None,
        session_title: str | None = None,
        images: list[str] | None = None,
    ) -> None:
        received.update(text=text, images=images)

    adapter._on_message = on_message
    await adapter._handle_photo(mock_update, None)

    assert received["text"] == "describe this chart"
    images = received["images"]
    assert isinstance(images, list) and len(images) == 1
    blob = _decode(images[0])
    assert blob[:2] == b"\xff\xd8"
    dims = jpeg_dimensions(images[0])
    assert dims is not None and max(dims) <= 1024
    assert len(blob) <= _VISION_MAX_JPEG_BYTES
    mock_message.reply_text.assert_not_called()
