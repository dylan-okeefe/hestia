"""Unit tests for the IdentityCompiler."""

import hashlib

import pytest

from hestia.config import IdentityConfig
from hestia.identity.compiler import IdentityCompiler


class TestDeterministicCompiler:
    """Tests for the deterministic markdown extraction."""

    def test_compile_returns_none_when_no_soul_path(self, tmp_path):
        """Compiler returns None when soul_path is None."""
        config = IdentityConfig(soul_path=None)
        compiler = IdentityCompiler(config)
        result = compiler.compile()
        assert result is None

    def test_compile_returns_none_when_soul_md_missing(self, tmp_path):
        """Compiler returns None when soul.md doesn't exist."""
        config = IdentityConfig(soul_path=tmp_path / "nonexistent.md")
        compiler = IdentityCompiler(config)
        result = compiler.compile()
        assert result is None

    def test_compile_extracts_text_from_markdown(self, tmp_path):
        """Compiler extracts text from simple markdown."""
        soul_md = tmp_path / "soul.md"
        soul_md.write_text("# Personality\n\nYou are helpful and kind.")

        config = IdentityConfig(soul_path=soul_md, max_tokens=1000)
        compiler = IdentityCompiler(config)
        result = compiler.compile()

        assert result is not None
        assert result.text == "Personality:\nYou are helpful and kind."
        assert not result.truncated

    def test_compile_strips_code_blocks(self, tmp_path):
        """Compiler strips code blocks from markdown."""
        soul_md = tmp_path / "soul.md"
        soul_md.write_text(
            "# Personality\n\n```python\nprint('hello')\n```\n\nYou are helpful."
        )

        config = IdentityConfig(soul_path=soul_md, max_tokens=1000)
        compiler = IdentityCompiler(config)
        result = compiler.compile()

        assert result is not None
        assert "print" not in result.text
        assert "You are helpful" in result.text

    def test_compile_strips_inline_code(self, tmp_path):
        """Compiler strips inline code markers."""
        soul_md = tmp_path / "soul.md"
        soul_md.write_text("Use `code` sparingly.")

        config = IdentityConfig(soul_path=soul_md, max_tokens=1000)
        compiler = IdentityCompiler(config)
        result = compiler.compile()

        assert result is not None
        assert "`" not in result.text
        assert "code" in result.text

    def test_compile_converts_links_to_text(self, tmp_path):
        """Compiler keeps link text but removes URL."""
        soul_md = tmp_path / "soul.md"
        soul_md.write_text("Visit [our docs](https://example.com) for more.")

        config = IdentityConfig(soul_path=soul_md, max_tokens=1000)
        compiler = IdentityCompiler(config)
        result = compiler.compile()

        assert result is not None
        assert "[our docs]" not in result.text
        assert "our docs" in result.text
        assert "https://example.com" not in result.text

    def test_compile_strips_images(self, tmp_path):
        """Compiler strips images entirely."""
        soul_md = tmp_path / "soul.md"
        soul_md.write_text("![alt text](image.png)\n\nYou are helpful.")

        config = IdentityConfig(soul_path=soul_md, max_tokens=1000)
        compiler = IdentityCompiler(config)
        result = compiler.compile()

        assert result is not None
        assert "!" not in result.text
        assert "alt text" not in result.text
        assert "image.png" not in result.text
        assert "You are helpful" in result.text

    def test_compile_strips_list_markers(self, tmp_path):
        """Compiler strips list markers but keeps content."""
        soul_md = tmp_path / "soul.md"
        soul_md.write_text("# Traits\n\n- Kind\n- Helpful\n- Patient")

        config = IdentityConfig(soul_path=soul_md, max_tokens=1000)
        compiler = IdentityCompiler(config)
        result = compiler.compile()

        assert result is not None
        assert "- Kind" not in result.text
        assert "Kind" in result.text
        assert "Helpful" in result.text
        assert "Patient" in result.text

    def test_compile_strips_bold_italic(self, tmp_path):
        """Compiler strips bold/italic markers."""
        soul_md = tmp_path / "soul.md"
        soul_md.write_text("**Bold** and *italic* and __also__ and _more_")

        config = IdentityConfig(soul_path=soul_md, max_tokens=1000)
        compiler = IdentityCompiler(config)
        result = compiler.compile()

        assert result is not None
        assert "**" not in result.text
        assert "*" not in result.text
        assert "__" not in result.text
        assert "_" not in result.text
        assert "Bold" in result.text
        assert "italic" in result.text

    def test_compile_produces_correct_hash(self, tmp_path):
        """Compiler produces correct SHA256 hash of source."""
        soul_md = tmp_path / "soul.md"
        content = "# Test\n\nContent here."
        soul_md.write_text(content)

        expected_hash = hashlib.sha256(content.encode()).hexdigest()

        config = IdentityConfig(soul_path=soul_md, max_tokens=1000)
        compiler = IdentityCompiler(config)
        result = compiler.compile()

        assert result is not None
        assert result.source_hash == expected_hash


class TestTruncation:
    """Tests for max_tokens truncation."""

    def test_large_soul_md_is_truncated(self, tmp_path):
        """Large soul.md is truncated from bottom, not rejected."""
        soul_md = tmp_path / "soul.md"
        # Create content that will exceed max_tokens * 4 chars
        # max_tokens=10 means max_chars=40
        lines = [f"Line {i}: This is some content." for i in range(20)]
        soul_md.write_text("\n".join(lines))

        config = IdentityConfig(soul_path=soul_md, max_tokens=10)
        compiler = IdentityCompiler(config)
        result = compiler.compile()

        assert result is not None
        assert result.truncated
        # Should be truncated to ~40 chars
        assert len(result.text) <= 45  # Allow small margin

    def test_small_soul_md_not_truncated(self, tmp_path):
        """Small soul.md is not truncated."""
        soul_md = tmp_path / "soul.md"
        soul_md.write_text("Short.")

        config = IdentityConfig(soul_path=soul_md, max_tokens=100)
        compiler = IdentityCompiler(config)
        result = compiler.compile()

        assert result is not None
        assert not result.truncated
        assert result.text == "Short."


class TestCaching:
    """Tests for compilation caching."""

    def test_cache_is_created(self, tmp_path):
        """Cache file is created after compilation."""
        soul_md = tmp_path / "soul.md"
        soul_md.write_text("Content.")

        cache_path = tmp_path / "cache.txt"
        config = IdentityConfig(
            soul_path=soul_md, compiled_cache_path=cache_path, max_tokens=100
        )
        compiler = IdentityCompiler(config)
        result = compiler.compile()

        assert result is not None
        assert cache_path.exists()

    def test_cache_contains_hash_and_content(self, tmp_path):
        """Cache file contains hash, truncated flag, and content."""
        soul_md = tmp_path / "soul.md"
        soul_md.write_text("Content.")

        cache_path = tmp_path / "cache.txt"
        config = IdentityConfig(
            soul_path=soul_md, compiled_cache_path=cache_path, max_tokens=100
        )
        compiler = IdentityCompiler(config)
        compiler.compile()

        cache_content = cache_path.read_text()
        lines = cache_content.split("\n", 2)
        assert len(lines) == 3
        assert len(lines[0]) == 64  # SHA256 hex hash
        assert lines[1] == "truncated=False"
        assert lines[2] == "Content."

    def test_cache_is_reused_when_unchanged(self, tmp_path):
        """Cached result is reused when soul.md hasn't changed."""
        soul_md = tmp_path / "soul.md"
        soul_md.write_text("Content.")

        cache_path = tmp_path / "cache.txt"
        config = IdentityConfig(
            soul_path=soul_md, compiled_cache_path=cache_path, max_tokens=100
        )

        # First compilation
        compiler1 = IdentityCompiler(config)
        result1 = compiler1.compile()
        assert result1 is not None

        # Second compilation (should use cache)
        compiler2 = IdentityCompiler(config)
        result2 = compiler2.compile()
        assert result2 is not None

        assert result1.text == result2.text
        assert result1.source_hash == result2.source_hash

    def test_recompile_when_changed(self, tmp_path):
        """Recompilation occurs when soul.md changes."""
        soul_md = tmp_path / "soul.md"
        soul_md.write_text("Original.")

        cache_path = tmp_path / "cache.txt"
        config = IdentityConfig(
            soul_path=soul_md, compiled_cache_path=cache_path, max_tokens=100
        )

        # First compilation
        compiler1 = IdentityCompiler(config)
        result1 = compiler1.compile()

        # Modify soul.md
        soul_md.write_text("Modified content.")

        # Second compilation (should detect change)
        compiler2 = IdentityCompiler(config)
        result2 = compiler2.compile()

        assert result1.text != result2.text
        assert result1.source_hash != result2.source_hash

    def test_recompile_on_change_false_ignores_changes(self, tmp_path):
        """When recompile_on_change=False, cache is always used."""
        soul_md = tmp_path / "soul.md"
        soul_md.write_text("Original.")

        cache_path = tmp_path / "cache.txt"
        config = IdentityConfig(
            soul_path=soul_md,
            compiled_cache_path=cache_path,
            max_tokens=100,
            recompile_on_change=False,
        )

        # First compilation
        compiler1 = IdentityCompiler(config)
        result1 = compiler1.compile()

        # Modify soul.md
        soul_md.write_text("Modified content.")

        # Second compilation (should use cache despite change)
        compiler2 = IdentityCompiler(config)
        result2 = compiler2.compile()

        assert result1.text == result2.text
        assert result1.source_hash == result2.source_hash


class TestGetCompiledText:
    """Tests for the get_compiled_text convenience method."""

    def test_get_compiled_text_returns_empty_when_no_soul(self, tmp_path):
        """Returns empty string when no soul.md exists."""
        config = IdentityConfig(soul_path=None)
        compiler = IdentityCompiler(config)
        assert compiler.get_compiled_text() == ""

    def test_get_compiled_text_returns_content(self, tmp_path):
        """Returns compiled text when soul.md exists."""
        soul_md = tmp_path / "soul.md"
        soul_md.write_text("# Test\n\nContent.")

        config = IdentityConfig(soul_path=soul_md, max_tokens=100)
        compiler = IdentityCompiler(config)
        text = compiler.get_compiled_text()

        assert text == "Test:\nContent."


class TestContextBuilderIntegration:
    """Tests for ContextBuilder integration with identity."""

    @pytest.mark.asyncio
    async def test_compiled_identity_appears_in_system_message(self, tmp_path):
        """Compiled identity appears at start of system message."""
        from hestia.context.builder import ContextBuilder
        from hestia.core.types import Session, SessionState, SessionTemperature

        # Create a mock policy
        class MockPolicy:
            def turn_token_budget(self, session):
                return 4000

        # Create a mock inference client
        class MockInference:
            async def tokenize(self, text: str) -> list[int]:
                return [0] * (len(text) // 4 + 1)

            async def tokenize_batch(self, texts: list[str]) -> list[int]:
                import asyncio

                results = await asyncio.gather(*(self.tokenize(t) for t in texts))
                return [len(r) for r in results]

            async def count_request(self, messages, tools):
                return sum(len(m.content or "") // 4 for m in messages)

        soul_md = tmp_path / "soul.md"
        soul_md.write_text("# Identity\n\nYou are a helpful assistant.")

        config = IdentityConfig(soul_path=soul_md, max_tokens=100)
        compiler = IdentityCompiler(config)
        compiled_identity = compiler.get_compiled_text()

        policy = MockPolicy()
        inference = MockInference()
        builder = ContextBuilder(
            inference_client=inference, policy=policy, identity_prefix=compiled_identity
        )

        session = Session(
            id="test",
            platform="test",
            platform_user="user",
            started_at=None,  # type: ignore[arg-type]
            last_active_at=None,  # type: ignore[arg-type]
            slot_id=None,
            slot_saved_path=None,
            state=SessionState.ACTIVE,
            temperature=SessionTemperature.COLD,
        )

        result = await builder.build(
            session=session,
            history=[],
            system_prompt="You are helpful.",
            tools=[],
        )

        # First message should be system with identity prefix
        assert len(result.messages) == 1
        system_msg = result.messages[0]
        assert system_msg.role == "system"
        assert "Identity:" in system_msg.content
        assert "You are helpful." in system_msg.content
        assert system_msg.content.startswith("Identity:")
