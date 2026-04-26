"""Tests for skills experimental feature flag."""


import pytest
from click.testing import CliRunner

from hestia.cli import cli
from hestia.errors import ExperimentalFeatureError
from hestia.skills.decorator import skill
from hestia.skills.types import SkillContext, SkillResult


class TestSkillDecoratorFlag:
    """Test @skill decorator requires HESTIA_EXPERIMENTAL_SKILLS."""

    def test_skill_decorator_without_flag_raises(self, monkeypatch):
        """Using @skill without the env var raises ExperimentalFeatureError."""
        monkeypatch.delenv("HESTIA_EXPERIMENTAL_SKILLS", raising=False)

        with pytest.raises(ExperimentalFeatureError, match="experimental preview"):
            @skill(name="test", description="Test skill")
            async def test_skill_fn(context: SkillContext) -> SkillResult:
                return SkillResult(summary="done")

    def test_skill_decorator_with_flag_works(self, monkeypatch):
        """Using @skill with the env var set works normally."""
        monkeypatch.setenv("HESTIA_EXPERIMENTAL_SKILLS", "1")

        @skill(name="test", description="Test skill")
        async def test_skill_fn(context: SkillContext) -> SkillResult:
            return SkillResult(summary="done")

        assert hasattr(test_skill_fn, "__hestia_skill__")
        assert test_skill_fn.__hestia_skill__.name == "test"


class TestCliSkillsFlag:
    """Test CLI skills commands require HESTIA_EXPERIMENTAL_SKILLS."""

    def test_cli_skills_list_disabled_message(self, monkeypatch):
        """Invoking hestia skill list without flag prints error and exits nonzero."""
        monkeypatch.delenv("HESTIA_EXPERIMENTAL_SKILLS", raising=False)
        runner = CliRunner()
        result = runner.invoke(cli, ["skill", "list"])
        assert result.exit_code != 0
        assert "experimental preview" in result.output.lower()

    def test_cli_skills_list_with_flag_works(self, monkeypatch):
        """Invoking hestia skill list with flag passes the gate."""
        monkeypatch.setenv("HESTIA_EXPERIMENTAL_SKILLS", "1")
        # Use a targeted approach: check that _check_experimental_skills
        # doesn't exit when the flag is set.
        from hestia.cli import _check_experimental_skills

        # Should not raise or exit
        _check_experimental_skills()
