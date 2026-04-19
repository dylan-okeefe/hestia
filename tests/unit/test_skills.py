"""Unit tests for skills system."""

import pytest

from hestia.persistence.db import Database
from hestia.persistence.skill_store import SkillRecord, SkillStore
from hestia.skills.decorator import skill, SkillDefinition
from hestia.skills.index import SkillIndexBuilder
from hestia.skills.state import SkillState
from hestia.skills.types import SkillContext, SkillResult


@pytest.fixture(autouse=True)
def enable_experimental_skills(monkeypatch):
    """Enable experimental skills for all tests in this module."""
    monkeypatch.setenv("HESTIA_EXPERIMENTAL_SKILLS", "1")


class TestSkillState:
    """Test skill lifecycle states."""

    def test_state_values(self):
        """Skill states have expected string values."""
        assert SkillState.DRAFT.value == "draft"
        assert SkillState.TESTED.value == "tested"
        assert SkillState.TRUSTED.value == "trusted"
        assert SkillState.DEPRECATED.value == "deprecated"
        assert SkillState.DISABLED.value == "disabled"

    def test_state_from_string(self):
        """Can create state from string."""
        assert SkillState("draft") == SkillState.DRAFT
        assert SkillState("tested") == SkillState.TESTED
        assert SkillState("trusted") == SkillState.TRUSTED


class TestSkillDecorator:
    """Test the @skill decorator."""

    def test_decorator_attaches_metadata(self):
        """@skill attaches metadata to functions."""

        @skill(
            name="test_skill",
            description="A test skill",
            required_tools=["tool1", "tool2"],
            capabilities=["cap1"],
            state=SkillState.DRAFT,
        )
        async def test_skill_fn(context: SkillContext) -> SkillResult:
            return SkillResult(summary="done")

        assert hasattr(test_skill_fn, "__hestia_skill__")
        meta: SkillDefinition = test_skill_fn.__hestia_skill__
        assert meta.name == "test_skill"
        assert meta.description == "A test skill"
        assert meta.required_tools == ["tool1", "tool2"]
        assert meta.capabilities == ["cap1"]
        assert meta.state == SkillState.DRAFT

    def test_decorator_defaults(self):
        """@skill has sensible defaults."""

        @skill(
            name="minimal_skill",
            description="Minimal skill",
        )
        async def minimal_skill_fn(context: SkillContext) -> SkillResult:
            return SkillResult(summary="done")

        meta: SkillDefinition = minimal_skill_fn.__hestia_skill__
        assert meta.required_tools == []
        assert meta.capabilities == []
        assert meta.state == SkillState.DRAFT


class TestSkillContext:
    """Test SkillContext class."""

    @pytest.mark.asyncio
    async def test_call_tool_without_caller_raises(self):
        """Calling tool without tool caller raises RuntimeError."""
        ctx = SkillContext(session_id="sess_1", user_input="test")
        with pytest.raises(RuntimeError, match="No tool caller configured"):
            await ctx.call_tool("some_tool")

    @pytest.mark.asyncio
    async def test_search_memory_without_store_raises(self):
        """Searching memory without store raises RuntimeError."""
        ctx = SkillContext(session_id="sess_1", user_input="test")
        with pytest.raises(RuntimeError, match="No memory store configured"):
            await ctx.search_memory("query")

    @pytest.mark.asyncio
    async def test_save_memory_without_store_raises(self):
        """Saving memory without store raises RuntimeError."""
        ctx = SkillContext(session_id="sess_1", user_input="test")
        with pytest.raises(RuntimeError, match="No memory store configured"):
            await ctx.save_memory("content")


class TestSkillResult:
    """Test SkillResult dataclass."""

    def test_result_defaults(self):
        """SkillResult has sensible defaults."""
        result = SkillResult(summary="test")
        assert result.summary == "test"
        assert result.status == "success"
        assert result.artifacts == []
        assert result.metadata == {}

    def test_result_full(self):
        """SkillResult can hold all fields."""
        result = SkillResult(
            summary="test",
            status="partial",
            artifacts=["art_1"],
            metadata={"key": "value"},
        )
        assert result.status == "partial"
        assert result.artifacts == ["art_1"]
        assert result.metadata == {"key": "value"}


class TestSkillStore:
    """Test SkillStore persistence."""

    @pytest.fixture
    async def skill_store(self, tmp_path):
        """Create a SkillStore with a fresh in-memory database."""
        db = Database("sqlite+aiosqlite:///:memory:")
        await db.connect()
        await db.create_tables()
        store = SkillStore(db)
        yield store
        await db.close()

    @pytest.mark.asyncio
    async def test_upsert_and_get(self, skill_store):
        """Can upsert a skill and retrieve it."""
        record = SkillRecord(
            id="skill_1",
            name="test_skill",
            description="A test skill",
            file_path="/path/to/skill.py",
            state=SkillState.DRAFT,
            capabilities=["network_egress"],
            required_tools=["http_get"],
        )
        await skill_store.upsert(record)

        retrieved = await skill_store.get_by_name("test_skill")
        assert retrieved is not None
        assert retrieved.name == "test_skill"
        assert retrieved.description == "A test skill"
        assert retrieved.state == SkillState.DRAFT

    @pytest.mark.asyncio
    async def test_get_by_name_not_found(self, skill_store):
        """Getting non-existent skill returns None."""
        result = await skill_store.get_by_name("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_all(self, skill_store):
        """Can list all skills."""
        await skill_store.upsert(SkillRecord(
            id="s1", name="skill_1", description="First", file_path="/a.py", state=SkillState.DRAFT,
        ))
        await skill_store.upsert(SkillRecord(
            id="s2", name="skill_2", description="Second", file_path="/b.py", state=SkillState.TRUSTED,
        ))

        records = await skill_store.list_all()
        assert len(records) == 2
        names = [r.name for r in records]
        assert "skill_1" in names
        assert "skill_2" in names

    @pytest.mark.asyncio
    async def test_list_all_filter_by_state(self, skill_store):
        """Can filter skills by state."""
        await skill_store.upsert(SkillRecord(
            id="s1", name="skill_1", description="First", file_path="/a.py", state=SkillState.DRAFT,
        ))
        await skill_store.upsert(SkillRecord(
            id="s2", name="skill_2", description="Second", file_path="/b.py", state=SkillState.TRUSTED,
        ))

        records = await skill_store.list_all(state=SkillState.TRUSTED)
        assert len(records) == 1
        assert records[0].name == "skill_2"

    @pytest.mark.asyncio
    async def test_list_all_exclude_disabled(self, skill_store):
        """Can exclude disabled skills from listing."""
        await skill_store.upsert(SkillRecord(
            id="s1", name="skill_1", description="First", file_path="/a.py", state=SkillState.DRAFT,
        ))
        await skill_store.upsert(SkillRecord(
            id="s2", name="skill_2", description="Second", file_path="/b.py", state=SkillState.DISABLED,
        ))

        records = await skill_store.list_all(exclude_disabled=True)
        assert len(records) == 1
        assert records[0].name == "skill_1"

    @pytest.mark.asyncio
    async def test_update_state(self, skill_store):
        """Can update skill state."""
        await skill_store.upsert(SkillRecord(
            id="s1", name="skill_1", description="First", file_path="/a.py", state=SkillState.DRAFT,
        ))

        success = await skill_store.update_state("skill_1", SkillState.TESTED)
        assert success is True

        record = await skill_store.get_by_name("skill_1")
        assert record.state == SkillState.TESTED

    @pytest.mark.asyncio
    async def test_update_state_not_found(self, skill_store):
        """Updating non-existent skill returns False."""
        success = await skill_store.update_state("nonexistent", SkillState.TRUSTED)
        assert success is False

    @pytest.mark.asyncio
    async def test_record_run(self, skill_store):
        """Can record skill execution."""
        await skill_store.upsert(SkillRecord(
            id="s1", name="skill_1", description="First", file_path="/a.py", state=SkillState.DRAFT,
        ))

        success = await skill_store.record_run("skill_1", failed=False)
        assert success is True

        record = await skill_store.get_by_name("skill_1")
        assert record.run_count == 1
        assert record.failure_count == 0
        assert record.last_run_at is not None

    @pytest.mark.asyncio
    async def test_record_run_failure(self, skill_store):
        """Can record failed skill execution."""
        await skill_store.upsert(SkillRecord(
            id="s1", name="skill_1", description="First", file_path="/a.py", state=SkillState.DRAFT,
        ))

        await skill_store.record_run("skill_1", failed=True)

        record = await skill_store.get_by_name("skill_1")
        assert record.run_count == 1
        assert record.failure_count == 1

    @pytest.mark.asyncio
    async def test_delete(self, skill_store):
        """Can delete a skill."""
        await skill_store.upsert(SkillRecord(
            id="s1", name="skill_1", description="First", file_path="/a.py", state=SkillState.DRAFT,
        ))

        success = await skill_store.delete("skill_1")
        assert success is True

        record = await skill_store.get_by_name("skill_1")
        assert record is None

    @pytest.mark.asyncio
    async def test_delete_not_found(self, skill_store):
        """Deleting non-existent skill returns False."""
        success = await skill_store.delete("nonexistent")
        assert success is False


class TestSkillIndexBuilder:
    """Test SkillIndexBuilder."""

    @pytest.fixture
    async def index_builder(self, tmp_path):
        """Create a SkillIndexBuilder with a fresh database."""
        db = Database("sqlite+aiosqlite:///:memory:")
        await db.connect()
        await db.create_tables()
        store = SkillStore(db)
        builder = SkillIndexBuilder(store)
        yield builder
        await db.close()

    @pytest.mark.asyncio
    async def test_empty_index(self, index_builder):
        """Empty skill store produces informative index."""
        index = await index_builder.build_index()
        assert index.skill_count == 0
        assert index.trusted_count == 0
        assert "No skills defined" in index.text

    @pytest.mark.asyncio
    async def test_index_with_skills(self, index_builder):
        """Index lists available skills."""
        # Add skills
        await index_builder._store.upsert(SkillRecord(
            id="s1", name="daily_briefing",
            description="Fetch weather and summarize",
            file_path="/skills/briefing.py",
            state=SkillState.TRUSTED,
            capabilities=["network_egress", "memory_read"],
            required_tools=["http_get"],
        ))
        await index_builder._store.upsert(SkillRecord(
            id="s2", name="weekly_review",
            description="Summarize weekly activity",
            file_path="/skills/review.py",
            state=SkillState.DRAFT,
            capabilities=["memory_read"],
            required_tools=["search_memory"],
        ))

        index = await index_builder.build_index()
        assert index.skill_count == 2
        assert index.trusted_count == 1
        assert "daily_briefing" in index.text
        assert "weekly_review" in index.text
        assert "trusted" in index.text
        assert "draft" in index.text
        assert "run_skill" in index.text

    @pytest.mark.asyncio
    async def test_index_excludes_disabled(self, index_builder):
        """Index excludes disabled skills by default."""
        await index_builder._store.upsert(SkillRecord(
            id="s1", name="active_skill",
            description="Active",
            file_path="/a.py",
            state=SkillState.TRUSTED,
        ))
        await index_builder._store.upsert(SkillRecord(
            id="s2", name="disabled_skill",
            description="Disabled",
            file_path="/b.py",
            state=SkillState.DISABLED,
        ))

        index = await index_builder.build_index()
        assert index.skill_count == 1
        assert "active_skill" in index.text
        assert "disabled_skill" not in index.text

    @pytest.mark.asyncio
    async def test_index_includes_disabled_when_requested(self, index_builder):
        """Index can include disabled skills when requested."""
        await index_builder._store.upsert(SkillRecord(
            id="s1", name="disabled_skill",
            description="Disabled",
            file_path="/b.py",
            state=SkillState.DISABLED,
        ))

        index = await index_builder.build_index(include_disabled=True)
        assert index.skill_count == 1
        assert "disabled_skill" in index.text

    @pytest.mark.asyncio
    async def test_format_for_prompt(self, index_builder):
        """Can format skill list for prompt."""
        skills = [
            SkillRecord(
                id="s1", name="skill_1",
                description="First skill",
                file_path="/a.py",
                state=SkillState.TRUSTED,
                capabilities=["cap1"],
            ),
        ]

        text = index_builder.format_for_prompt(skills)
        assert "Available skills:" in text
        assert "skill_1" in text
        assert "First skill" in text
        assert "trusted" in text
        assert "cap1" in text

    @pytest.mark.asyncio
    async def test_format_for_prompt_empty(self, index_builder):
        """Formatting empty skill list returns empty string."""
        text = index_builder.format_for_prompt([])
        assert text == ""
