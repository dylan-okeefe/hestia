"""ArtifactStore with inline + file-backed storage and TTL.

Async callers MUST NOT call ``store`` / ``fetch*`` / ``gc`` directly from
inside an event loop — the underlying filesystem I/O is synchronous and
would stall every concurrent task on the loop. Two accommodations exist:

1. ``await ArtifactStore.open(root, default_ttl=...)`` — async factory
   that runs the construction-time mkdir + inline-index load in
   ``asyncio.to_thread`` and returns a ready-to-use store.
2. From async contexts, wrap calls in ``asyncio.to_thread`` at the call
   site (see :mod:`hestia.tools.registry` and
   :mod:`hestia.tools.builtin.read_artifact`).

Direct ``ArtifactStore(root)`` construction remains supported for CLI
startup (``make_app``, which runs before the event loop) and for
synchronous unit tests. Inside an async context, prefer ``open()``.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import secrets
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from hestia.errors import ArtifactExpiredError, ArtifactNotFoundError

INLINE_THRESHOLD_BYTES = 64 * 1024  # 64 KB
DEFAULT_TTL_SECONDS = 24 * 60 * 60  # 24 h


@dataclass
class ArtifactMetadata:
    """Metadata for a stored artifact."""

    handle: str
    size_bytes: int
    content_type: str  # "text/plain", "application/json", "application/octet-stream"
    created_at: float  # unix timestamp
    expires_at: float
    source_tool: str | None
    preview: str  # first 200 chars for model-visible descriptions


@dataclass
class Artifact:
    """Full artifact with metadata and content."""

    metadata: ArtifactMetadata
    content: bytes  # always bytes at the storage layer


class ArtifactStore:
    """Storage for large content referenced by opaque handles.

    Small content (< 64KB) is stored inline in memory + JSON index.
    Large content is stored as files on disk.
    All artifacts have TTL and can be garbage collected.
    """

    def __init__(
        self,
        root: Path | None = None,
        default_ttl: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        """Initialize the artifact store (sync).

        Runs ``root.mkdir(parents=True, exist_ok=True)`` and loads the
        inline index from ``root/inline.json`` synchronously. Acceptable
        from sync contexts (CLI startup in ``make_app``, unit tests).
        **Not safe to call from inside a running event loop** — use
        :meth:`open` instead.

        Args:
            root: Directory for file-backed artifacts. Defaults to .hestia/artifacts/
            default_ttl: Default TTL in seconds for new artifacts
        """
        self._root = root or Path(".hestia/artifacts")
        self._default_ttl = default_ttl
        self._inline: dict[str, bytes] = {}  # handle -> content for small artifacts

        self._root.mkdir(parents=True, exist_ok=True)
        self._load_inline_index()

    @classmethod
    async def open(
        cls,
        root: Path | None = None,
        default_ttl: int = DEFAULT_TTL_SECONDS,
    ) -> ArtifactStore:
        """Async factory that performs construction-time I/O off the event loop.

        Prefer this over direct ``__init__`` when constructing an
        :class:`ArtifactStore` from inside async code — the sync
        ``__init__`` does mkdir + JSON load, which stalls the loop.
        """
        return await asyncio.to_thread(cls, root, default_ttl)

    def _load_inline_index(self) -> None:
        """Load inline artifact index from disk."""
        index_path = self._root / "inline.json"
        if index_path.exists():
            with open(index_path) as f:
                data = json.load(f)
                for handle, content_b64 in data.get("content", {}).items():
                    self._inline[handle] = base64.b64decode(content_b64)

    def _atomic_write_json(self, path: Path, data: dict[str, Any]) -> None:
        """Write JSON to disk atomically: temp file in same dir + os.replace().

        Prevents corruption if the process crashes mid-write.
        """
        fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f)
            os.replace(tmp_path, path)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp_path)
            raise

    def _save_inline_index(self) -> None:
        """Save inline artifact index to disk."""
        index_path = self._root / "inline.json"
        data = {
            "content": {
                handle: base64.b64encode(content).decode("ascii")
                for handle, content in self._inline.items()
            }
        }
        self._atomic_write_json(index_path, data)

    def _generate_handle(self) -> str:
        """Generate an opaque handle.

        Format: art_ + 10 hex chars (5 bytes from secrets)
        """
        return "art_" + secrets.token_hex(5)

    def store(
        self,
        content: bytes | str,
        content_type: str = "text/plain",
        source_tool: str | None = None,
        ttl: int | None = None,
    ) -> str:
        """Store content and return a handle.

        Args:
            content: Content to store (bytes or string)
            content_type: MIME type of content
            source_tool: Name of tool that created this artifact
            ttl: TTL in seconds, or None for default

        Returns:
            Opaque handle for retrieving the artifact
        """
        # Normalize to bytes
        content_bytes = content.encode("utf-8") if isinstance(content, str) else content

        handle = self._generate_handle()
        now = time.time()
        ttl_to_use = ttl if ttl is not None else self._default_ttl
        expires_at = now + ttl_to_use

        # Create metadata
        preview = content_bytes[:200].decode("utf-8", errors="replace")
        metadata = ArtifactMetadata(
            handle=handle,
            size_bytes=len(content_bytes),
            content_type=content_type,
            created_at=now,
            expires_at=expires_at,
            source_tool=source_tool,
            preview=preview,
        )

        # Store content
        if len(content_bytes) <= INLINE_THRESHOLD_BYTES:
            # Small content: store inline
            self._inline[handle] = content_bytes
            self._save_inline_index()
        else:
            # Large content: store as file
            content_path = self._root / f"{handle}.bin"
            with open(content_path, "wb") as f:
                f.write(content_bytes)

        # Store metadata
        metadata_path = self._root / f"{handle}.json"
        self._atomic_write_json(metadata_path, asdict(metadata))

        return handle

    def fetch_metadata(self, handle: str) -> ArtifactMetadata:
        """Fetch artifact metadata.

        Args:
            handle: Artifact handle

        Returns:
            ArtifactMetadata

        Raises:
            ArtifactNotFoundError: if artifact doesn't exist
            ArtifactExpiredError: if artifact has expired
        """
        metadata_path = self._root / f"{handle}.json"
        if not metadata_path.exists():
            raise ArtifactNotFoundError(f"Artifact not found: {handle}")

        with open(metadata_path) as f:
            data = json.load(f)
            metadata = ArtifactMetadata(**data)

        # Check expiration
        if time.time() > metadata.expires_at:
            raise ArtifactExpiredError(f"Artifact expired: {handle}")

        return metadata

    def fetch_content(self, handle: str) -> bytes:
        """Fetch artifact content.

        Args:
            handle: Artifact handle

        Returns:
            Content as bytes

        Raises:
            ArtifactNotFoundError: if artifact doesn't exist or content missing
            ArtifactExpiredError: if artifact has expired
        """
        # Check metadata exists (will raise if not found or expired)
        self.fetch_metadata(handle)

        # Try inline first
        if handle in self._inline:
            return self._inline[handle]

        # Try file
        content_path = self._root / f"{handle}.bin"
        if content_path.exists():
            with open(content_path, "rb") as f:
                return f.read()

        raise ArtifactNotFoundError(f"Artifact metadata exists but content missing: {handle}")

    def fetch(self, handle: str) -> Artifact:
        """Fetch full artifact (metadata + content).

        Args:
            handle: Artifact handle

        Returns:
            Artifact with metadata and content
        """
        metadata = self.fetch_metadata(handle)
        content = self.fetch_content(handle)
        return Artifact(metadata=metadata, content=content)

    def list(self) -> list[ArtifactMetadata]:
        """List all non-expired artifacts.

        Returns:
            List of ArtifactMetadata, newest first.
        """
        results: list[ArtifactMetadata] = []
        now = time.time()

        for metadata_path in self._root.glob("*.json"):
            if metadata_path.name == "inline.json":
                continue

            try:
                with open(metadata_path) as f:
                    data = json.load(f)
                    metadata = ArtifactMetadata(**data)

                if now <= metadata.expires_at:
                    results.append(metadata)
            except (json.JSONDecodeError, OSError, TypeError):
                continue

        results.sort(key=lambda m: m.created_at, reverse=True)
        return results

    def delete(self, handle: str) -> bool:
        """Delete an artifact by handle.

        Returns:
            True if the artifact was found and deleted.
        """
        metadata_path = self._root / f"{handle}.json"
        if not metadata_path.exists():
            return False

        with contextlib.suppress(OSError):
            metadata_path.unlink()

        content_path = self._root / f"{handle}.bin"
        with contextlib.suppress(OSError):
            content_path.unlink()

        if handle in self._inline:
            del self._inline[handle]
            self._save_inline_index()

        return True

    def gc(self) -> int:
        """Garbage collect expired artifacts.

        Returns:
            Number of artifacts removed
        """
        removed = 0
        now = time.time()

        # Check all metadata files
        for metadata_path in self._root.glob("*.json"):
            if metadata_path.name == "inline.json":
                continue

            try:
                with open(metadata_path) as f:
                    data = json.load(f)
                    metadata = ArtifactMetadata(**data)

                if now > metadata.expires_at:
                    # Remove metadata
                    metadata_path.unlink()

                    # Remove content if file-backed
                    content_path = self._root / f"{metadata.handle}.bin"
                    if content_path.exists():
                        content_path.unlink()

                    # Remove from inline if present
                    if metadata.handle in self._inline:
                        del self._inline[metadata.handle]

                    removed += 1
            except (json.JSONDecodeError, OSError):
                # Skip corrupted files
                continue

        # Save inline index if we removed anything
        if removed > 0:
            self._save_inline_index()

        return removed
