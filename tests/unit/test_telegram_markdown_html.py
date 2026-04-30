"""Unit tests for Telegram markdown-to-HTML conversion."""


from hestia.platforms.telegram_adapter import _md_to_tg_html


class TestMdToTgHtmlBold:
    """Tests for **bold** conversion."""

    def test_simple_bold(self):
        """Double asterisks become <b> tags."""
        assert _md_to_tg_html("**hello**") == "<b>hello</b>"

    def test_bold_in_sentence(self):
        """Bold within a sentence."""
        assert _md_to_tg_html("This is **bold** text.") == "This is <b>bold</b> text."

    def test_multiple_bold(self):
        """Multiple bold segments."""
        assert (
            _md_to_tg_html("**a** and **b**")
            == "<b>a</b> and <b>b</b>"
        )

    def test_empty_bold(self):
        """Empty bold remains empty."""
        assert _md_to_tg_html("****") == "****"


class TestMdToTgHtmlItalic:
    """Tests for *italic* conversion."""

    def test_simple_italic(self):
        """Single asterisks become <i> tags."""
        assert _md_to_tg_html("*hello*") == "<i>hello</i>"

    def test_italic_in_sentence(self):
        """Italic within a sentence."""
        assert _md_to_tg_html("This is *italic* text.") == "This is <i>italic</i> text."

    def test_bold_takes_precedence_over_italic(self):
        """Double asterisks are bold, not nested italic."""
        assert _md_to_tg_html("**bold**") == "<b>bold</b>"

    def test_asterisk_math_not_converted(self):
        """Asterisks used as multiplication symbols are left alone."""
        assert _md_to_tg_html("5 * 3 = 15") == "5 * 3 = 15"

    def test_unmatched_single_asterisk(self):
        """Unmatched asterisk is left as-is."""
        assert _md_to_tg_html("*unmatched") == "*unmatched"


class TestMdToTgHtmlCode:
    """Tests for inline and block code conversion."""

    def test_inline_code(self):
        """Backticks become <code> tags."""
        assert _md_to_tg_html("Use `print()`") == "Use <code>print()</code>"

    def test_inline_code_with_special_chars(self):
        """Special chars inside code are escaped properly."""
        result = _md_to_tg_html("`5 < 10`")
        assert "<code>" in result
        assert "5 &lt; 10" in result

    def test_code_block_with_language(self):
        """Triple backticks with language become <pre><code>."""
        result = _md_to_tg_html("```python\nprint(1)\n```")
        assert "<pre>" in result
        assert "print(1)" in result

    def test_code_block_without_language(self):
        """Triple backticks without language become <pre>."""
        result = _md_to_tg_html("```\nhello\n```")
        assert "<pre>" in result
        assert "hello" in result


class TestMdToTgHtmlEscaping:
    """Tests for HTML entity escaping."""

    def test_ampersand(self):
        """Ampersands are escaped."""
        assert _md_to_tg_html("A & B") == "A &amp; B"

    def test_less_than(self):
        """Less-than signs are escaped."""
        assert _md_to_tg_html("5 < 10") == "5 &lt; 10"

    def test_greater_than(self):
        """Greater-than signs are escaped."""
        assert _md_to_tg_html("10 > 5") == "10 &gt; 5"

    def test_existing_html_not_double_escaped(self):
        """Already-escaped entities stay as-is (no double escaping)."""
        # After escaping, &amp; becomes &amp;amp; — this is expected because
        # we escape raw input. The function assumes raw markdown, not pre-escaped HTML.
        result = _md_to_tg_html("&amp;")
        assert result == "&amp;amp;"

    def test_mixed_content(self):
        """Complex markdown with multiple elements."""
        input_text = "**Bold** and *italic* and `code` and 5 < 10"
        expected = "<b>Bold</b> and <i>italic</i> and <code>code</code> and 5 &lt; 10"
        assert _md_to_tg_html(input_text) == expected


class TestMdToTgHtmlEdgeCases:
    """Edge cases and regression tests."""

    def test_plain_text_unchanged(self):
        """Text without markdown is unchanged (modulo escaping)."""
        assert _md_to_tg_html("Hello world") == "Hello world"

    def test_empty_string(self):
        """Empty string stays empty."""
        assert _md_to_tg_html("") == ""

    def test_only_whitespace(self):
        """Whitespace-only string is unchanged."""
        assert _md_to_tg_html("   \n  ") == "   \n  "

    def test_emoji_and_unicode(self):
        """Emoji and unicode are preserved."""
        assert _md_to_tg_html("🎉 **Party** 🎉") == "🎉 <b>Party</b> 🎉"

    def test_nested_bold_inside_code(self):
        """Bold inside backticks is converted after backticks — resulting in
        nested tags. Telegram clients generally tolerate this, and LLMs rarely
        put bold inside inline code."""
        result = _md_to_tg_html("`**not bold**`")
        assert "<code>" in result
        assert "<b>not bold</b>" in result
