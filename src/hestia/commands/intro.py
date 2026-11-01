"""Detailed narrated intro routine for Hestia.

The intro is the long-form counterpart to /tour: it walks a user through
every major subsystem with concrete commands and accurate limits. Like the
tour it is pure narration — progression is via /continue, and /endtour stops
it — but unlike the tour it is allowed in group rooms, because onboarding
frequently happens in the group chat where a new user was invited.

All facts here are ground-truthed against the running configuration
(3 slots x 131,072-token context, manual /compact, model
qwen3.8-flash-next-iq3_s, ~40 tools). If those change, update these steps —
an inaccurate intro is worse than none.
"""

from __future__ import annotations

from collections.abc import Callable

from hestia.commands.tour import TourStore, render_tour_continue, render_tour_end

IntroStep = Callable[[], str]


class IntroStore:
    """Ephemeral cursor store for the intro routine.

    Keyed by ``(platform, platform_user)`` exactly like TourStore, but kept
    as a separate singleton so /tour and /intro never clobber each other's
    cursor. A process restart clears all intros.
    """

    def __init__(self) -> None:
        self._cursors: dict[tuple[str, str], int] = {}

    def _key(self, platform: str, platform_user: str) -> tuple[str, str]:
        return (platform.lower(), platform_user)

    def get(self, platform: str, platform_user: str) -> int | None:
        """Return the next step index for a conversation, or ``None``."""
        return self._cursors.get(self._key(platform, platform_user))

    def set(self, platform: str, platform_user: str, cursor: int) -> None:
        """Set the next step index for a conversation."""
        self._cursors[self._key(platform, platform_user)] = cursor

    def clear(self, platform: str, platform_user: str) -> None:
        """Clear the cursor for a conversation."""
        self._cursors.pop(self._key(platform, platform_user), None)


# Module-level singleton shared by command handlers and platform adapters.
DEFAULT_INTRO_STORE = IntroStore()


def get_intro_store() -> IntroStore:
    """Return the default intro store."""
    return DEFAULT_INTRO_STORE


def _step_welcome() -> str:
    return (
        "Welcome to Hestia — a local-first AI assistant that runs on Dylan's "
        "machine and answers on Telegram, Matrix, a web dashboard, and the CLI. "
        "I'm running the qwen3.8-flash-next model (IQ3_S quantized) on local "
        "inference, with about 40 tools for web browsing, email, files, job "
        "searching, and automation. This intro has 13 steps — type /continue "
        "for each next step, /endtour to stop."
    )


def _step_sessions() -> str:
    return (
        "First, the basics. Every chat with me is a *session*: one session per "
        "Telegram DM, per group chat, and per Matrix room — each with its own "
        "conversation history and its own memory thread. Hestia runs 3 context "
        "slots in parallel, each holding 131,072 tokens of context, so several "
        "conversations (plus background jobs) can be active at once. Useful "
        "commands: /session (current session info), /history (message log), "
        "/reset (archive this session and start fresh), /commands (full command "
        "list)."
    )


def _step_context_compaction() -> str:
    return (
        "Context & compaction — the most important thing to understand. "
        "Compaction is *manual*, not automatic. When a conversation fills its "
        "131k tokens, you'll get a context-limit error instead of silent "
        "summarization. What to do: /tokens shows usage; /compact summarizes "
        "and archives older turns in place (you can pass an instruction, e.g. "
        "'/compact keep the API decisions'); /reset starts over. Rule of thumb: "
        "when I tell you context is full, run /compact and re-state anything "
        "urgent I should carry forward."
    )


def _step_memory() -> str:
    return (
        "Memory is what survives compaction and new sessions — chat history "
        "does not. I save durable facts proactively (identity, preferences, "
        "corrections), and you can also just say 'remember that…' or 'forget "
        "that'. Two scopes: *global* memories load in every conversation; "
        "*topic*-scoped memories load only in conversations subscribed to that "
        "topic. Commands: /remember-global <fact>, /add-topic <name>, "
        "/remove-topic <name>, /topic (see subscriptions), /refresh (rebuild "
        "this session's memory). Ask me 'what do you know about me?' any time."
    )


def _step_groups() -> str:
    return (
        "Group chats: a group is one session with one shared context and one "
        "memory thread, keyed to the group itself. Be accurate about one "
        "limitation: Telegram forum *topics* inside a group are NOT separate "
        "sessions — every topic in a forum group shares the group's single "
        "context window. If you want truly separate threads, use separate "
        "groups (or DMs). Anyone in the group can talk to me; I reply in the "
        "group."
    )


def _step_access_trust() -> str:
    return (
        "Your access level. You're a standard user: I can read, browse, and "
        "draft freely, but anything sensitive — sending email, writing files, "
        "running shell commands, browser logins, spawning subagents — goes "
        "through a proposal/confirmation step first. You'll get a prompt you "
        "can approve or reject, and pending proposals can be reviewed on the "
        "dashboard's Proposals page or by asking me to list them. Nothing "
        "destructive runs without your explicit OK."
    )


def _step_web_ui() -> str:
    return (
        "The web dashboard: http://localhost:8765 on Dylan's machine, or "
        "http://192.168.1.71:8765 from other devices on the home network. "
        "Pages worth knowing: Proposals (approve/reject queued actions), "
        "Scheduler (recurring tasks), Browser Sessions (log into sites once — "
        "I reuse the saved session, and you can watch a live browser stream), "
        "Workflows (multi-step automations), Knowledge (browse/edit my "
        "memory), Sessions, and Security (audit log)."
    )


def _step_browsing() -> str:
    return (
        "Web browsing. http_get fetches plain pages; for JavaScript-heavy or "
        "login-walled sites I drive a real Chromium browser (browser_get, "
        "browser_interact, browser_get_json, browser_get_links). To get past "
        "logins, either ask me for browser_login — it opens a visible browser "
        "window, you log in and close it, and the session is saved — or use "
        "the dashboard's Browser Sessions page. Saved sessions are reused "
        "automatically on later fetches of the same domain."
    )


def _step_jobs() -> str:
    return (
        "Job hunting (a Hestia specialty). Dedicated searchers for LinkedIn, "
        "Indeed, Dice, Built In, and ZipRecruiter return structured listings "
        "with direct links. On top of that: a job-alert queue with a daily "
        "digest, extraction of job URLs straight out of alert emails, and "
        "scheduled searches — e.g. 'every weekday at 8am, search senior "
        "platform roles and queue anything new'. Try: 'search Indeed for "
        "remote Python jobs'."
    )


def _step_email() -> str:
    return (
        "Email. I have full IMAP/SMTP access: list, search, read, draft, "
        "move, and flag messages. I only *send* after you explicitly approve "
        "the draft — a proposal shows you the exact recipient, subject, and "
        "body first. Good patterns: 'draft a reply to the latest email from "
        "X', 'summarize this week's receipts', 'move all newsletters to the "
        "archive folder'."
    )


def _step_files_automation() -> str:
    return (
        "Files & automation. I can read, write, and edit files under "
        "~/Documents/Hestia-documents, search with grep/glob, produce large "
        "outputs as downloadable artifacts, and run terminal commands (with "
        "your approval). For repeating work: scheduled tasks take cron "
        "expressions ('0 9 * * 1-5'), and workflows chain multi-step actions "
        "with triggers. Both are manageable from chat or the dashboard. "
        "delegate_task also lets me spawn a subagent in its own slot for big "
        "parallel jobs."
    )


def _step_voice_extras() -> str:
    return (
        "Extras. On Telegram you can send voice notes — I transcribe them and "
        "can reply by voice. Other useful bits: read_clipboard, a style "
        "profile (tell me how formal/terse to be and I'll adapt), rollback "
        "to undo a bad turn, and /quit or /exit to end a CLI session. "
        "Anything you can't find: /commands lists everything."
    )


def _step_wrap_up() -> str:
    return (
        "That's the full intro. Suggested first moves: tell me a few standing "
        "preferences so I can save them to memory; log into one site via the "
        "dashboard's Browser Sessions page; and try one real task end-to-end. "
        "Re-run this intro any time with /intro, take the short tour with "
        "/tour, or just ask. Welcome aboard!"
    )


# Static list of intro steps. Order here is the order users see.
INTRO_STEPS: list[IntroStep] = [
    _step_welcome,
    _step_sessions,
    _step_context_compaction,
    _step_memory,
    _step_groups,
    _step_access_trust,
    _step_web_ui,
    _step_browsing,
    _step_jobs,
    _step_email,
    _step_files_automation,
    _step_voice_extras,
    _step_wrap_up,
]


def _render_step(step_index: int) -> str:
    """Render a single intro step by index."""
    if not 0 <= step_index < len(INTRO_STEPS):
        raise ValueError(f"Invalid intro step index: {step_index}")
    return INTRO_STEPS[step_index]()


def _header(step_index: int) -> str:
    """Return the 'Intro step N of M' header."""
    return f"Intro step {step_index + 1} of {len(INTRO_STEPS)}"


def render_intro_start(
    store: IntroStore,
    platform: str,
    platform_user: str,
) -> str:
    """Start the intro and return the message to send.

    Unlike the tour, the intro is allowed in group rooms — onboarding often
    happens in the group a new user was invited to. The cursor is keyed by
    the room/chat id either way.
    """
    store.set(platform, platform_user, 1)
    return f"{_header(0)}\n\n{_render_step(0)}"


def render_intro_continue(
    store: IntroStore,
    platform: str,
    platform_user: str,
) -> str:
    """Advance the intro by one step and return the message to send."""
    cursor = store.get(platform, platform_user)
    if cursor is None:
        return "No intro running."

    if cursor >= len(INTRO_STEPS):
        store.clear(platform, platform_user)
        return "Intro complete. You're all set!"

    text = f"{_header(cursor)}\n\n{_render_step(cursor)}"
    store.set(platform, platform_user, cursor + 1)
    return text


def render_intro_end(
    store: IntroStore,
    platform: str,
    platform_user: str,
) -> str:
    """End the intro and return the message to send."""
    if store.get(platform, platform_user) is None:
        return "No intro running."

    store.clear(platform, platform_user)
    return "Intro ended."


def render_continue(
    intro_store: IntroStore,
    tour_store: TourStore,
    platform: str,
    platform_user: str,
    group_room: bool = False,
) -> str:
    """Advance whichever routine is active: intro first, then tour."""
    if intro_store.get(platform, platform_user) is not None:
        return render_intro_continue(intro_store, platform, platform_user)
    return render_tour_continue(
        tour_store, platform, platform_user, group_room=group_room
    )


def render_end(
    intro_store: IntroStore,
    tour_store: TourStore,
    platform: str,
    platform_user: str,
    group_room: bool = False,
) -> str:
    """End whichever routine is active: intro first, then tour."""
    if intro_store.get(platform, platform_user) is not None:
        return render_intro_end(intro_store, platform, platform_user)
    return render_tour_end(tour_store, platform, platform_user, group_room=group_room)
