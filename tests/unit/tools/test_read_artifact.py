"""Unit tests for read_artifact chunked reads."""

from __future__ import annotations

import pytest

from hestia.artifacts.store import ArtifactStore
from hestia.tools.builtin.read_artifact import make_read_artifact_tool


@pytest.fixture
def artifact_store(tmp_path):
    return ArtifactStore(root=tmp_path, default_ttl=3600)


@pytest.fixture
def read_artifact(artifact_store):
    return make_read_artifact_tool(artifact_store)


class TestReadArtifactChunks:
    """Chunked reading of artifact content."""

    @pytest.mark.anyio
    async def test_reads_full_content_from_zero(self, read_artifact, artifact_store):
        content = "Hello, artifact!"
        handle = artifact_store.store(content)

        result = await read_artifact(handle=handle, start_at=0, length=4000)
        assert "Hello, artifact!" in result
        assert "bytes 0-16 of 16" in result

    @pytest.mark.anyio
    async def test_reads_subsequent_chunk(self, read_artifact, artifact_store):
        content = "ABCDEFGHIJ" * 100  # 1000 chars
        handle = artifact_store.store(content)

        result = await read_artifact(handle=handle, start_at=500, length=200)
        assert "bytes 500-700 of 1000" in result
        assert result.endswith(content[500:700])

    @pytest.mark.anyio
    async def test_clamps_to_end(self, read_artifact, artifact_store):
        content = "short"
        handle = artifact_store.store(content)

        result = await read_artifact(handle=handle, start_at=2, length=1000)
        assert "bytes 2-5 of 5" in result
        assert result.endswith("ort")

    @pytest.mark.anyio
    async def test_past_end_reports_eof(self, read_artifact, artifact_store):
        content = "tiny"
        handle = artifact_store.store(content)

        result = await read_artifact(handle=handle, start_at=10, length=100)
        assert "offset 10 is past end of 4 chars" in result

    @pytest.mark.anyio
    async def test_negative_start_clamps_to_zero(self, read_artifact, artifact_store):
        content = "abc"
        handle = artifact_store.store(content)

        result = await read_artifact(handle=handle, start_at=-5, length=4000)
        assert "bytes 0-3 of 3" in result

    @pytest.mark.anyio
    async def test_missing_handle(self, read_artifact):
        result = await read_artifact(handle="art_doesnotexist", start_at=0, length=4000)
        assert "Artifact not found" in result

    @pytest.mark.anyio
    async def test_chunk_not_reartifacted_by_registry(self, artifact_store):
        """A 4000-char chunk should fit within read_artifact's own max_inline_chars."""
        from hestia.tools.registry import ToolRegistry

        content = "X" * 20_000
        handle = artifact_store.store(content)
        tool = make_read_artifact_tool(artifact_store)
        registry = ToolRegistry(artifact_store)
        registry.register(tool)

        raw = await tool(handle=handle, start_at=4000, length=4000)
        assert len(raw) <= 8000
        assert "bytes 4000-8000 of 20000" in raw
