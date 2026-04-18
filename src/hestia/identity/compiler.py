"""Identity compiler for SOUL.md (operator personality).

Compiles a SOUL.md personality document into a compact, bounded identity view
that gets prepended to the system prompt. Uses deterministic extraction by default:
- Parse markdown, extract text under each heading
- Concatenate as flat text block, stripping markdown syntax
- Truncate from bottom if over max_tokens
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from hestia.config import IdentityConfig


@dataclass
class CompileResult:
    """Result of compiling a SOUL.md file."""

    text: str  # The compiled identity view
    source_hash: str  # Hash of the source file for cache validation
    truncated: bool  # Whether truncation was applied


class IdentityCompiler:
    """Compiles SOUL.md to a compact identity view.

    Default strategy: deterministic extraction (no model call needed).
    Extracts text under each markdown heading, flattens to text, truncates
    from bottom if over max_tokens.
    """

    def __init__(self, config: IdentityConfig) -> None:
        """Initialize with identity configuration.

        Args:
            config: IdentityConfig with soul_path, max_tokens, etc.
        """
        self._config = config

    def compile(self) -> CompileResult | None:
        """Compile SOUL.md to a compact identity view.

        Returns:
            CompileResult with the compiled text, or None if the file is missing
            or soul_path is None.
        """
        if self._config.soul_path is None:
            return None

        soul_path = self._config.soul_path
        if not soul_path.exists():
            return None

        content = soul_path.read_text(encoding="utf-8")
        source_hash = hashlib.sha256(content.encode()).hexdigest()

        # Check cache if recompile_on_change is disabled (use cached version regardless of changes)
        if not self._config.recompile_on_change:
            cached = self._check_cache_any()
            if cached is not None:
                return cached

        # Deterministic extraction: flatten markdown, extract text
        compiled = self._extract_text(content)

        # Truncate if over max_tokens (rough approximation: 4 chars per token)
        max_chars = self._config.max_tokens * 4
        truncated = False
        if len(compiled) > max_chars:
            compiled = compiled[:max_chars]
            truncated = True

        result = CompileResult(
            text=compiled,
            source_hash=source_hash,
            truncated=truncated,
        )

        # Save to cache
        self._save_cache(result)

        return result

    def _extract_text(self, content: str) -> str:
        """Extract text from markdown content.

        Strategy:
        1. Remove code blocks (```...```)
        2. Remove inline code (`...`)
        3. Remove markdown links, keeping link text
        4. Remove images
        5. Convert headings to plain text with colons
        6. Remove other markdown syntax (#, *, -, >, etc.)
        7. Collapse whitespace

        Args:
            content: Raw markdown content

        Returns:
            Flattened text suitable for prompt injection
        """
        text = content

        # Remove code blocks
        text = re.sub(r"```[\s\S]*?```", "", text)

        # Remove inline code markers, keep content
        text = re.sub(r"`([^`]*)`", r"\1", text)

        # Remove images entirely
        text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", "", text)

        # Convert markdown links to just the text
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

        # Convert headings to plain text with newlines
        # Handle # Heading, ## Heading, etc.
        text = re.sub(r"^#{1,6}\s+(.+)$", r"\1:", text, flags=re.MULTILINE)

        # Remove horizontal rules
        text = re.sub(r"^---+$", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\*\*\*+$", "", text, flags=re.MULTILINE)

        # Remove list markers but keep content
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)

        # Remove blockquote markers
        text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)

        # Remove bold/italic markers
        text = re.sub(r"\*\*\*([^*]+)\*\*\*", r"\1", text)
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"\*([^*]+)\*", r"\1", text)
        text = re.sub(r"___([^_]+)___", r"\1", text)
        text = re.sub(r"__([^_]+)__", r"\1", text)
        text = re.sub(r"_([^_]+)_", r"\1", text)

        # Collapse multiple newlines
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Clean up whitespace
        lines = [line.strip() for line in text.split("\n")]
        lines = [line for line in lines if line]  # Remove empty lines

        return "\n".join(lines)

    def _check_cache(self, source_hash: str) -> CompileResult | None:
        """Check if a cached result exists and matches the source hash.

        Args:
            source_hash: Hash of the current source file

        Returns:
            Cached CompileResult if valid and hash matches, None otherwise
        """
        cache_path = self._config.compiled_cache_path
        if not cache_path.exists():
            return None

        try:
            cache_content = cache_path.read_text(encoding="utf-8")
            lines = cache_content.split("\n", 2)
            if len(lines) < 3:
                return None

            cached_hash = lines[0].strip()
            truncated_str = lines[1].strip()
            text = lines[2]

            if cached_hash != source_hash:
                return None

            return CompileResult(
                text=text,
                source_hash=cached_hash,
                truncated=truncated_str == "truncated=True",
            )
        except OSError:
            return None

    def _check_cache_any(self) -> CompileResult | None:
        """Check if any cached result exists (for recompile_on_change=False).

        Returns:
            Cached CompileResult if exists, None otherwise
        """
        cache_path = self._config.compiled_cache_path
        if not cache_path.exists():
            return None

        try:
            cache_content = cache_path.read_text(encoding="utf-8")
            lines = cache_content.split("\n", 2)
            if len(lines) < 3:
                return None

            cached_hash = lines[0].strip()
            truncated_str = lines[1].strip()
            text = lines[2]

            return CompileResult(
                text=text,
                source_hash=cached_hash,
                truncated=truncated_str == "truncated=True",
            )
        except OSError:
            return None

    def _save_cache(self, result: CompileResult) -> None:
        """Save the compilation result to cache.

        Args:
            result: CompileResult to cache
        """
        cache_path = self._config.compiled_cache_path
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_content = (
                f"{result.source_hash}\n"
                f"truncated={result.truncated}\n"
                f"{result.text}"
            )
            cache_path.write_text(cache_content, encoding="utf-8")
        except OSError:
            # Cache failure is non-fatal
            pass

    def get_compiled_text(self) -> str:
        """Get the compiled identity text, or empty string if not available.

        Returns:
            The compiled identity view, or "" if SOUL.md isn't available
        """
        result = self.compile()
        if result is None:
            return ""
        return result.text
