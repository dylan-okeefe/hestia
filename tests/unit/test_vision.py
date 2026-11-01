"""L234 vision tests: helpers, serialization, client gating matrix, config wiring."""

from __future__ import annotations

import base64
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.config import InferenceConfig, TelegramConfig
from hestia.core.inference import InferenceClient
from hestia.core.serialization import message_to_dict
from hestia.core.types import Message
from hestia.core.vision import estimate_image_tokens, estimate_images_tokens, jpeg_dimensions


# A minimal synthetic baseline JPEG: SOI, SOF0 (8x16), EOI. Enough for the
# dimension parser; not a displayable image (that path is covered by the
# real-ffmpeg integration tests).
def _synthetic_jpeg_data_url(width: int, height: int) -> str:
    sof0 = (
        b"\xff\xc0"  # SOF0 marker
        b"\x00\x0b"  # segment length
        b"\x08"  # precision
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x01\x01\x11\x00"  # 1 component
    )
    blob = b"\xff\xd8" + sof0 + b"\xff\xd9"
    return "data:image/jpeg;base64," + base64.b64encode(blob).decode("ascii")


_IMG_8X16 = _synthetic_jpeg_data_url(8, 16)
_IMG_1024 = _synthetic_jpeg_data_url(1024, 768)


class TestJpegDimensions:
    def test_parses_synthetic_jpeg(self) -> None:
        assert jpeg_dimensions(_IMG_8X16) == (8, 16)

    def test_ignores_non_jpeg_payload(self) -> None:
        url = "data:image/jpeg;base64," + base64.b64encode(b"not a jpeg at all").decode("ascii")
        assert jpeg_dimensions(url) is None

    def test_rejects_non_data_url(self) -> None:
        assert jpeg_dimensions("https://example.com/x.jpg") is None

    def test_rejects_malformed_base64(self) -> None:
        assert jpeg_dimensions("data:image/jpeg;base64,@@@not-base64@@@") is None


class TestTokenEstimate:
    def test_edge_divisor_math(self) -> None:
        # longest edge 16 → (16 // 28) ** 2 → clamped to 1
        assert estimate_image_tokens(_IMG_8X16) == 1

    def test_1024_edge_estimate(self) -> None:
        # (1024 // 28) ** 2 == 36 ** 2
        assert estimate_image_tokens(_IMG_1024) == 1296

    def test_fallback_when_undecodable(self) -> None:
        url = "data:image/jpeg;base64," + base64.b64encode(b"garbage").decode("ascii")
        # fallback edge 1024 → 1296
        assert estimate_image_tokens(url) == 1296

    def test_sum_helper(self) -> None:
        assert estimate_images_tokens([_IMG_8X16, _IMG_1024]) == 1 + 1296


class TestMessageSerialization:
    def test_text_only_message_unchanged(self) -> None:
        d = message_to_dict(Message(role="user", content="hello"))
        assert d == {"role": "user", "content": "hello"}

    def test_image_message_emits_content_array(self) -> None:
        d = message_to_dict(
            Message(role="user", content="look", images=[_IMG_8X16, _IMG_1024])
        )
        assert d["role"] == "user"
        assert d["content"][0] == {"type": "text", "text": "look"}
        assert d["content"][1] == {"type": "image_url", "image_url": {"url": _IMG_8X16}}
        assert d["content"][2] == {"type": "image_url", "image_url": {"url": _IMG_1024}}

    def test_empty_images_list_keeps_plain_content(self) -> None:
        d = message_to_dict(Message(role="user", content="hi", images=[]))
        assert d["content"] == "hi"


def _make_client(vision: bool, server_type: str) -> InferenceClient:
    return InferenceClient(
        "http://localhost:8001",
        "my-model.gguf",
        server_type=server_type,
        vision_enabled=vision,
    )


def _stub_chat(client: InferenceClient) -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]
    }
    client._request = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]


def _user_msg_with_image() -> Message:
    return Message(role="user", content="describe this", images=[_IMG_1024])


class TestVisionGatingMatrix:
    """L234 §1/§4: images flow ONLY when vision=True AND server_type=openai-compat."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("vision", [True, False])
    @pytest.mark.parametrize("server_type", ["openai-compat", "llamacpp"])
    async def test_gating_matrix(
        self, vision: bool, server_type: str, caplog: Any
    ) -> None:
        client = _make_client(vision, server_type)
        _stub_chat(client)
        messages = [Message(role="system", content="sys"), _user_msg_with_image()]

        with caplog.at_level(logging.INFO):
            await client.chat(messages)

        body = client._request.call_args.kwargs["json_payload"]  # type: ignore[attr-defined]
        user_part = body["messages"][1]
        allowed = vision and server_type == "openai-compat"
        if allowed:
            assert isinstance(user_part["content"], list)
            assert user_part["content"][0] == {"type": "text", "text": "describe this"}
            assert user_part["content"][1] == {
                "type": "image_url",
                "image_url": {"url": _IMG_1024},
            }
            # Estimated image-token cost is logged per request (§3).
            assert any(
                "estimated image tokens" in r.message and r.levelno == logging.INFO
                for r in caplog.records
            )
        else:
            assert user_part["content"] == "describe this"
            # Misconfig must be visible: a strip warning, never silent.
            assert any(
                "Stripping" in r.message and r.levelno == logging.WARNING
                for r in caplog.records
            )

    @pytest.mark.asyncio
    async def test_llamacpp_startup_warning_when_vision_enabled(self, caplog: Any) -> None:
        """vision=True + llamacpp: startup WARNING (§1), before any request."""
        with caplog.at_level(logging.WARNING):
            _make_client(vision=True, server_type="llamacpp")
        assert any(
            "telegram.vision=True" in r.message and "stripped" in r.message
            for r in caplog.records
        )

    def test_no_startup_warning_when_aligned(self, caplog: Any) -> None:
        with caplog.at_level(logging.WARNING):
            _make_client(vision=True, server_type="openai-compat")
            _make_client(vision=False, server_type="llamacpp")
        assert not any("telegram.vision=True" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_historical_images_ride_in_later_requests(self) -> None:
        """Session-history coherence (§3): an older image message keeps its parts."""
        client = _make_client(vision=True, server_type="openai-compat")
        _stub_chat(client)
        messages = [
            _user_msg_with_image(),
            Message(role="assistant", content="a chart"),
            Message(role="user", content="and now?"),
        ]
        await client.chat(messages)
        body = client._request.call_args.kwargs["json_payload"]  # type: ignore[attr-defined]
        assert body["messages"][0]["content"][1]["type"] == "image_url"
        # The follow-up text-only message stays plain.
        assert body["messages"][2]["content"] == "and now?"

    @pytest.mark.asyncio
    async def test_streaming_path_applies_same_gate(self, caplog: Any) -> None:
        """chat_stream strips images under llamacpp just like chat()."""
        client = _make_client(vision=False, server_type="openai-compat")

        async def _aiter_lines() -> Any:
            yield 'data: {"choices":[{"delta":{"content":"hi"}}]}'
            yield "data: [DONE]"

        mock_response = MagicMock()
        mock_response.aiter_lines = _aiter_lines
        mock_response.raise_for_status = MagicMock()
        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream.__aexit__ = AsyncMock(return_value=None)
        client._client.stream = MagicMock(return_value=mock_stream)  # type: ignore[method-assign]

        with caplog.at_level(logging.WARNING):
            async for _ in client.chat_stream([_user_msg_with_image()]):
                pass

        call_kwargs = client._client.stream.call_args.kwargs  # type: ignore[attr-defined]
        assert call_kwargs["json"]["messages"][0]["content"] == "describe this"
        assert any("Stripping" in r.message for r in caplog.records)


class TestVisionConfigWiring:
    def test_telegram_vision_defaults(self) -> None:
        cfg = TelegramConfig()
        assert cfg.vision is False
        assert cfg.vision_max_images_per_message == 4
        assert cfg.vision_max_edge_px == 1024

    def test_telegram_vision_from_env(self) -> None:
        cfg = TelegramConfig.from_env(
            {
                "HESTIA_TELEGRAM_VISION": "true",
                "HESTIA_TELEGRAM_VISION_MAX_IMAGES_PER_MESSAGE": "2",
                "HESTIA_TELEGRAM_VISION_MAX_EDGE_PX": "768",
            }
        )
        assert cfg.vision is True
        assert cfg.vision_max_images_per_message == 2
        assert cfg.vision_max_edge_px == 768

    def test_inference_server_type_default_and_env(self) -> None:
        assert InferenceConfig().server_type == "llamacpp"
        cfg = InferenceConfig.from_env({"HESTIA_INFERENCE_SERVER_TYPE": "openai-compat"})
        assert cfg.server_type == "openai-compat"

    def test_inference_server_type_rejected(self) -> None:
        with pytest.raises(ValueError, match="server_type"):
            InferenceConfig(server_type="strata-ish")  # type: ignore[arg-type]
