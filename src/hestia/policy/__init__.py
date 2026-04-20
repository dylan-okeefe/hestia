"""Hestia policy engine.

This package exposes the :class:`PolicyEngine` interface plus the
:class:`DefaultPolicyEngine` reference implementation, and a small set of
shared constants used by the policy layer *and* by diagnostic callsites
(notably ``hestia doctor``) that need to report the same numbers that
drive behavior.

Constants live here so that the ``0.85`` context-pressure threshold and
the handful of platform-name string literals aren't repeated — and can't
silently drift — across files (M-6 and M-12 in the Copilot audit).
"""

from typing import Final, Literal

#: Fraction of the per-turn token budget at which
#: :meth:`DefaultPolicyEngine.should_compress` trips, and the same
#: fraction of ``ctx_window`` that :meth:`DefaultPolicyEngine.turn_token_budget`
#: treats as usable for input after reserving response headroom.
#:
#: Kept as a module-level ``Final`` constant so the ``hestia doctor``
#: diagnostic output displays the exact number the engine uses —
#: Copilot M-6 flagged the previous ``0.85`` literal duplicated between
#: ``policy/default.py`` and ``commands.py``.
CONTEXT_PRESSURE_THRESHOLD: Final[float] = 0.85

#: Tokens reserved out of the context window for the model's response
#: in :meth:`DefaultPolicyEngine.turn_token_budget`. Not currently
#: duplicated elsewhere but kept symmetrical with
#: :data:`CONTEXT_PRESSURE_THRESHOLD` so future diagnostic callers have
#: a named handle.
TURN_RESPONSE_RESERVE_TOKENS: Final[int] = 2048

#: Canonical platform-name string constants. ``Session.platform`` is a
#: free-form ``str`` (DB-backed; platform adapters outside this repo
#: may coin their own names), so we cannot safely migrate the field's
#: static type to a closed ``Literal``. But the *framework's own*
#: comparisons — policy gating for subagent / scheduler, doctor
#: reporting — must all spell the names the same way. These constants
#: make that contract explicit (M-12).
PLATFORM_SUBAGENT: Final[str] = "subagent"
PLATFORM_SCHEDULER: Final[str] = "scheduler"
PLATFORM_CLI: Final[str] = "cli"

#: Informational ``Literal`` alias. Use for signatures that *promise* to
#: only receive one of these platforms (e.g. subagent internals). The
#: canonical source of truth for comparisons at runtime is the string
#: constants above — prefer ``session.platform == PLATFORM_SUBAGENT``
#: over ``cast(PlatformName, session.platform) == "subagent"``.
PlatformName = Literal["cli", "subagent", "scheduler"]

__all__ = [
    "CONTEXT_PRESSURE_THRESHOLD",
    "PLATFORM_CLI",
    "PLATFORM_SCHEDULER",
    "PLATFORM_SUBAGENT",
    "PlatformName",
    "TURN_RESPONSE_RESERVE_TOKENS",
]
