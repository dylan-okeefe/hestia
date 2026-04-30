"""Unit tests for InferenceClient.tokenize_batch."""

import pytest

from hestia.core.inference import InferenceClient


class CharTokenInferenceClient:
    """Fake inference client where each character maps to a unique token.

    This makes the separator-based batching deterministic and exact.
    """

    def __init__(self) -> None:
        self.model_name = "fake-model"

    async def tokenize(self, text: str) -> list[int]:
        return list(range(len(text)))

    async def tokenize_batch(self, texts: list[str]) -> list[int]:
        """Re-use the real implementation via explicit delegation."""
        return await InferenceClient.tokenize_batch(self, texts)  # type: ignore[arg-type]


class TestTokenizeBatch:
    """Tests for the separator-based batch tokenization."""

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self) -> None:
        """Batch tokenizing an empty list returns an empty list."""
        client = CharTokenInferenceClient()
        result = await client.tokenize_batch([])
        assert result == []

    @pytest.mark.asyncio
    async def test_single_text_matches_individual(self) -> None:
        """Batch with one text returns the same count as individual tokenize."""
        client = CharTokenInferenceClient()
        text = "hello world"
        batch_result = await client.tokenize_batch([text])
        individual = await client.tokenize(text)
        assert batch_result == [len(individual)]

    @pytest.mark.asyncio
    async def test_multiple_texts_match_individual_counts(self) -> None:
        """Batch counts match individual tokenize counts for each text."""
        client = CharTokenInferenceClient()
        texts = ["short", "a longer piece of text", "x"]
        batch_result = await client.tokenize_batch(texts)
        individual_counts = [len(await client.tokenize(t)) for t in texts]
        assert batch_result == individual_counts

    @pytest.mark.asyncio
    async def test_fallback_when_separator_in_text(self) -> None:
        """When separator appears in text, falls back to individual calls."""
        client = CharTokenInferenceClient()
        sep = "\x00\x00BATCH_SEPARATOR\x00\x00"
        texts = ["hello", f"contains{sep}separator", "world"]
        batch_result = await client.tokenize_batch(texts)
        individual_counts = [len(await client.tokenize(t)) for t in texts]
        assert batch_result == individual_counts

    @pytest.mark.asyncio
    async def test_varying_lengths(self) -> None:
        """Batch handles texts of very different lengths."""
        client = CharTokenInferenceClient()
        texts = ["", "a", "ab" * 100, "xyz"]
        batch_result = await client.tokenize_batch(texts)
        individual_counts = [len(await client.tokenize(t)) for t in texts]
        assert batch_result == individual_counts


class TestInferenceClientRealImplementation:
    """Tests using the real InferenceClient.tokenize_batch logic."""

    @pytest.mark.asyncio
    async def test_real_client_method_exists(self) -> None:
        """InferenceClient has tokenize_batch method."""
        client = InferenceClient("http://localhost:8001", "test.gguf")
        assert hasattr(client, "tokenize_batch")
        await client.close()
