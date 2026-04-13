"""Skill lifecycle states."""

from enum import StrEnum


class SkillState(StrEnum):
    """Lifecycle states for a skill.

    Skills progress through states as they mature:
    - draft: Initial state, under development
    - tested: Has been run in test mode at least once
    - trusted: Approved for production use
    - deprecated: Should not be used for new work
    - disabled: Cannot be invoked
    """

    DRAFT = "draft"
    TESTED = "tested"
    TRUSTED = "trusted"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"
