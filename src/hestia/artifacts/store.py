"""ArtifactStore with inline + file-backed storage and TTL."""

import json
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from hestia.errors import ArtifactError, ArtifactExpiredError, ArtifactNotFoundError

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
        """Initialize the artifact store.

        Args:
            root: Directory for file-backed artifacts. Defaults to .hestia/artifacts/
            default_ttl: Default TTL in seconds for new artifacts
        """
        self._root = root or Path(".hestia/artifacts")
        self._default_ttl = default_ttl
        self._inline: dict[str, bytes] = {}  # handle -> content for small artifacts

        # Ensure root exists
        self._root.mkdir(parents=True, exist_ok=True)

        # Load inline index if it exists
        self._load_inline_index()

    def _load_inline_index(self) -> None:
        """Load inline artifact index from disk."""
        index_path = self._root / "inline.json"
        if index_path.exists():
            with open(index_path, "r") as f:
                data = json.load(f)
                for handle, content_b64 in data.get("content", {}).items():
                    import base64

                    self._inline[handle] = base64.b64decode(content_b64)

    def _save_inline_index(self) -> None:
        """Save inline artifact index to disk."""
        index_path = self._root / "inline.json"
        import base64

        data = {
            "content": {
                handle: base64.b64encode(content).decode("ascii")
                for handle, content in self._inline.items()
            }
        }
        with open(index_path, "w") as f:
            json.dump(data, f)

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
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        else:
            content_bytes = content

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
        with open(metadata_path, "w") as f:
            json.dump(asdict(metadata), f)

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

        with open(metadata_path, "r") as f:
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
        metadata = self.fetch_metadata(handle)

        # Try inline first
        if handle in self._inline:
            return self._inline[handle]

        # Try file
        content_path = self._root / f"{handle}.bin"
        if content_path.exists():
            with open(content_path, "rb") as f:
                return f.read()

        raise ArtifactNotFoundError(
            f"Artifact metadata exists but content missing: {handle}"
        )

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
                with open(metadata_path, "r") as f:
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
