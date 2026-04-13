"""Skill index for prompt injection."""

from dataclasses import dataclass

from hestia.persistence.skill_store import SkillRecord, SkillStore
from hestia.skills.state import SkillState


@dataclass
class SkillIndex:
    """Compiled index of available skills for prompt injection."""

    text: str
    skill_count: int
    trusted_count: int


class SkillIndexBuilder:
    """Builds a compact skill index for inclusion in system prompts."""

    def __init__(self, skill_store: SkillStore):
        """Initialize with skill store.

        Args:
            skill_store: Store for skill records
        """
        self._store = skill_store

    async def build_index(
        self,
        include_disabled: bool = False,
    ) -> SkillIndex:
        """Build a skill index.

        The index is a compact text block listing available skills
        with their state and capabilities. Disabled skills are
        excluded unless include_disabled is True.

        Args:
            include_disabled: Whether to include disabled skills

        Returns:
            SkillIndex with compiled text and counts
        """
        records = await self._store.list_all(exclude_disabled=not include_disabled)

        if not records:
            return SkillIndex(
                text="No skills defined.",
                skill_count=0,
                trusted_count=0,
            )

        lines = ["Available skills:"]
        trusted_count = 0

        for record in records:
            # Format: - name: description [state, caps]
            caps = "+".join(record.capabilities) or "none"
            state_marker = record.state.value
            lines.append(
                f"- {record.name}: {record.description} "
                f"[{state_marker}, {caps}]"
            )
            if record.state == SkillState.TRUSTED:
                trusted_count += 1

        lines.append("\nTo run a skill, use: run_skill(name=\"skill_name\")")

        return SkillIndex(
            text="\n".join(lines),
            skill_count=len(records),
            trusted_count=trusted_count,
        )

    def format_for_prompt(self, records: list[SkillRecord]) -> str:
        """Format a list of skills for prompt injection.

        Args:
            records: Skill records to format

        Returns:
            Formatted text block
        """
        if not records:
            return ""

        lines = ["Available skills:"]
        for record in records:
            caps = "+".join(record.capabilities) or "none"
            state_marker = record.state.value
            lines.append(
                f"- {record.name}: {record.description} "
                f"[{state_marker}, {caps}]"
            )

        return "\n".join(lines)
