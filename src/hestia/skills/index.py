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

        This is a thin wrapper around :meth:`format_for_prompt` that adds
        store lookup, counts, and the ``run_skill`` instruction.
        ``format_for_prompt`` is the source of truth for the text format.

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

        # Keep formatting in one place to avoid silent divergence.
        text = self.format_for_prompt(records)
        text += "\n\nTo run a skill, use: run_skill(name=\"skill_name\")"

        trusted_count = sum(
            1 for record in records if record.state == SkillState.TRUSTED
        )

        return SkillIndex(
            text=text,
            skill_count=len(records),
            trusted_count=trusted_count,
        )

    def format_for_prompt(self, records: list[SkillRecord]) -> str:
        """Format a list of skills for prompt injection.

        This is the **canonical** formatting method for skill records.
        ``build_index`` delegates here for the text representation.
        Any change to the output shape must be made here.

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
