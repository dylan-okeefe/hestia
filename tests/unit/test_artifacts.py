"""Unit tests for ArtifactStore."""

import json

import pytest

from hestia.artifacts.store import INLINE_THRESHOLD_BYTES, ArtifactStore
from hestia.errors import ArtifactExpiredError, ArtifactNotFoundError


@pytest.fixture
def temp_store(tmp_path):
    """Create a temporary artifact store."""
    return ArtifactStore(root=tmp_path, default_ttl=3600)


class TestStoreAndFetch:
    """Tests for basic store/fetch operations."""

    def test_store_inline_content(self, temp_store):
        """Small content is stored inline."""
        content = b"Hello, world!"
        handle = temp_store.store(content, content_type="text/plain")

        assert handle.startswith("art_")
        assert len(handle) == 14  # art_ + 10 hex chars

        # Verify we can fetch it back
        fetched = temp_store.fetch_content(handle)
        assert fetched == content

    def test_store_large_content_file_backed(self, temp_store, tmp_path):
        """Large content (> 64KB) is stored as file."""
        content = b"x" * (INLINE_THRESHOLD_BYTES + 100)
        handle = temp_store.store(content)

        # Verify file was created
        content_path = tmp_path / f"{handle}.bin"
        assert content_path.exists()

        # Verify we can fetch it back
        fetched = temp_store.fetch_content(handle)
        assert fetched == content

    def test_store_string_content(self, temp_store):
        """String content is automatically encoded to bytes."""
        content = "Hello, 世界! 🌍"
        handle = temp_store.store(content)

        fetched = temp_store.fetch_content(handle)
        assert fetched.decode("utf-8") == content

    def test_fetch_full_artifact(self, temp_store):
        """fetch() returns both metadata and content."""
        content = b"test content"
        handle = temp_store.store(
            content,
            content_type="application/json",
            source_tool="test_tool",
        )

        artifact = temp_store.fetch(handle)
        assert artifact.metadata.handle == handle
        assert artifact.metadata.size_bytes == len(content)
        assert artifact.metadata.content_type == "application/json"
        assert artifact.metadata.source_tool == "test_tool"
        assert artifact.content == content

    def test_fetch_metadata_separately(self, temp_store):
        """fetch_metadata returns just metadata."""
        content = b"test"
        handle = temp_store.store(content, source_tool="my_tool")

        metadata = temp_store.fetch_metadata(handle)
        assert metadata.handle == handle
        assert metadata.source_tool == "my_tool"


class TestHandleFormat:
    """Tests for handle generation format."""

    def test_handle_format(self, temp_store):
        """Handles start with art_ and are unique."""
        handles = [temp_store.store(b"x") for _ in range(100)]

        # All unique
        assert len(set(handles)) == 100

        # All start with art_
        for h in handles:
            assert h.startswith("art_")
            assert len(h) == 14
            # Rest should be hex
            suffix = h[4:]
            assert all(c in "0123456789abcdef" for c in suffix)


class TestExpiration:
    """Tests for TTL and expiration."""

    def test_fetch_expired_raises(self, temp_store):
        """Fetching expired artifact raises ArtifactExpiredError."""
        content = b"expires soon"
        handle = temp_store.store(content, ttl=0)  # already expired

        # Should raise immediately since TTL=0
        with pytest.raises(ArtifactExpiredError):
            temp_store.fetch_content(handle)

    def test_gc_removes_expired(self, temp_store, tmp_path, monkeypatch):
        """gc() removes expired artifacts."""
        # Create some artifacts
        handle1 = temp_store.store(b"fresh", ttl=3600)  # 1 hour
        handle2 = temp_store.store(b"expired", ttl=0)  # already expired

        # Verify both exist
        assert temp_store.fetch_content(handle1) == b"fresh"

        # gc should remove expired
        removed = temp_store.gc()
        assert removed == 1

        # Expired one is gone
        with pytest.raises(ArtifactNotFoundError):
            temp_store.fetch_content(handle2)

        # Fresh one still works
        assert temp_store.fetch_content(handle1) == b"fresh"

    def test_gc_removes_file_backed_expired(self, temp_store, tmp_path):
        """gc() removes file-backed expired artifacts."""
        content = b"x" * (INLINE_THRESHOLD_BYTES + 100)
        handle = temp_store.store(content, ttl=0)

        content_path = tmp_path / f"{handle}.bin"
        assert content_path.exists()  # File was created

        removed = temp_store.gc()
        assert removed == 1

        # File is gone
        assert not content_path.exists()


class TestNotFound:
    """Tests for missing artifacts."""

    def test_fetch_missing_raises(self, temp_store):
        """Fetching non-existent handle raises ArtifactNotFoundError."""
        with pytest.raises(ArtifactNotFoundError):
            temp_store.fetch_content("art_nonexistent")

    def test_fetch_metadata_missing_raises(self, temp_store):
        """Fetching metadata for non-existent handle raises error."""
        with pytest.raises(ArtifactNotFoundError):
            temp_store.fetch_metadata("art_nonexistent")


class TestPreview:
    """Tests for preview generation."""

    def test_preview_is_first_200_chars(self, temp_store):
        """Preview contains first 200 chars of content."""
        content = "A" * 500
        handle = temp_store.store(content)

        metadata = temp_store.fetch_metadata(handle)
        assert len(metadata.preview) == 200
        assert metadata.preview == "A" * 200

    def test_preview_handles_unicode(self, temp_store):
        """Preview handles unicode content correctly."""
        content = "世界" * 100  # Multi-byte characters
        handle = temp_store.store(content)

        metadata = temp_store.fetch_metadata(handle)
        # Should not raise, preview should be valid string
        assert isinstance(metadata.preview, str)


class TestMetadataRoundTrip:
    """Tests for metadata JSON serialization."""

    def test_metadata_round_trips(self, temp_store):
        """Metadata survives JSON round-trip."""
        handle = temp_store.store(
            b"test",
            content_type="application/octet-stream",
            source_tool="test_tool",
            ttl=1234,
        )

        # Fetch fresh from disk
        metadata = temp_store.fetch_metadata(handle)
        assert metadata.handle == handle
        assert metadata.content_type == "application/octet-stream"
        assert metadata.source_tool == "test_tool"
        assert metadata.size_bytes == 4


class TestAtomicInlineIndex:
    """Tests for atomic write of inline index."""

    def test_inline_index_atomic_write(self, temp_store, tmp_path):
        """After _save_inline_index(), the file exists and is valid JSON."""
        temp_store.store(b"hello", content_type="text/plain")
        index_path = tmp_path / "inline.json"
        assert index_path.exists()
        with open(index_path) as f:
            data = json.load(f)
        assert "content" in data

    def test_inline_index_survives_crash(self, temp_store, tmp_path, monkeypatch):
        """If json.dump raises mid-write, original inline.json is unchanged."""
        # Create a valid inline index first
        temp_store.store(b"before", content_type="text/plain")
        index_path = tmp_path / "inline.json"
        assert index_path.exists()
        original_data = index_path.read_text()

        # Add more content, then make json.dump fail
        temp_store._inline["new_handle"] = b"after"


        def failing_dump(*args, **kwargs):
            raise RuntimeError("simulated crash")

        monkeypatch.setattr(json, "dump", failing_dump)

        with pytest.raises(RuntimeError, match="simulated crash"):
            temp_store._save_inline_index()

        # Original file should still be valid and unchanged
        assert index_path.read_text() == original_data


class TestAtomicMetadataWrite:
    """Tests for atomic write of per-artifact metadata."""

    def test_per_artifact_metadata_atomic_write(self, temp_store, tmp_path):
        """The {handle}.json metadata file must be written atomically."""
        handle = temp_store.store(b"hello", content_type="text/plain")
        metadata_path = tmp_path / f"{handle}.json"
        assert metadata_path.exists()
        with open(metadata_path) as f:
            data = json.load(f)
        assert data["handle"] == handle

    def test_per_artifact_metadata_survives_crash(self, temp_store, tmp_path, monkeypatch):
        """If json.dump raises mid-write, original metadata file is unchanged."""
        handle = temp_store.store(b"before", content_type="text/plain")
        metadata_path = tmp_path / f"{handle}.json"
        assert metadata_path.exists()
        original_data = metadata_path.read_text()

        def failing_dump(*args, **kwargs):
            raise RuntimeError("simulated crash")

        monkeypatch.setattr(json, "dump", failing_dump)

        with pytest.raises(RuntimeError, match="simulated crash"):
            temp_store._atomic_write_json(metadata_path, {"handle": "new"})

        # Original file should still be valid and unchanged
        assert metadata_path.read_text() == original_data
