# L43 — Voice Phase B: Telegram voice calls via py-tgcalls userbot

**Status:** Spec only. **Do not merge to `develop`.** Branch lives on
`origin/feature/voice-phase-b-calls*` until release-prep names it.

**Branch:** `feature/voice-phase-b-calls` (Cursor may decompose into
sub-branches `-a-scaffolding`, `-b-pipeline`, `-c-orchestrator-wiring`
based on Kimi's step budget; the launch plan calls out three sub-scopes
and explicitly leaves the split to Cursor).

**Depends on:** L41 (`feature/voice-shared-infra`). Forks from there,
not from `develop` and not from L42 (the two phases share infra but are
otherwise independent).

**Blocked on Dylan-side prereqs:**

1. **Dedicated phone number** for the Hestia userbot. Prepaid SIM
   strongly recommended over Google Voice / Twilio / JMP — Telegram
   has been rejecting virtual numbers more aggressively. ~$10-20
   one-time.
2. **Telegram API application** registered at
   [my.telegram.org/apps](https://my.telegram.org/apps) using that
   number. Note `api_id` and `api_hash`.
3. **`py-tgcalls` build verified** on the Ubuntu box. Ships native
   code; occasional distro-specific build issues. Likely
   `apt install libssl-dev libavcodec-dev libavformat-dev` will
   resolve common failures. Run the library's hello-world in an
   isolated venv first.
4. **Piper voice file** chosen and downloaded (or Kokoro voice if going
   higher quality immediately).
5. Dylan's own Telegram `user_id` (for the `allowed_caller_user_ids`
   list).

**Cursor MUST verify Dylan has provided 1-3 above before launching
Kimi on this loop.** If missing, KIMI_CURRENT stays in idle state and
chat tells Dylan what's needed.

---

## Architecture (finalized; ADR-0024 captures the rationale)

**Two Telegram identities:**

- The existing `@HestiaBot` continues handling text and (after L42 lands
  on develop) voice messages. L23 inline-keyboard confirmations stay
  intact.
- A new **userbot** — a regular Telegram user account driven via
  `pyrogram` + `py-tgcalls` — handles live VOIP calls on its own phone
  number.

Husband sees two contacts: "Hestia" (bot, for text and voice messages)
and "Hestia Voice" (userbot, for calls). Not ideal UX but no app
install required.

**Why not bot-only:** Telegram Bot API has no VOIP and has not added
it in years (verified 2026-04-18 against
[core.telegram.org/bots/api](https://core.telegram.org/bots/api)).

**Why not userbot-only:** Standard MTProto user accounts can't send
inline keyboard buttons the same way bots can. Collapsing to userbot
breaks L23's confirmation UX.

**Two-account cost:** one extra contact on husband's phone, one extra
phone number to maintain.

**Ban-risk discussion (in ADR-0024):** userbots for personal automation
are allowed by Telegram ToS. Risk goes up if the number receives many
inbound calls or starts sending automated messages. Mitigation:
allowed-caller list (rejects unknown numbers), no outbound messaging
from the userbot.

---

## Sub-scope A — userbot scaffolding + audio I/O (no STT/TTS yet)

**Branch (if splitting):** `feature/voice-phase-b-scaffolding`

**Files:**

- **New:** `src/hestia/adapters/telegram_voice.py` — `TelegramVoiceAdapter`
  class wrapping pyrogram `Client` + py-tgcalls.
- **Modified:** `src/hestia/config.py` — `TelegramVoiceConfig`:
  ```python
  @dataclass
  class TelegramVoiceConfig:
      enabled: bool = False
      api_id: int = 0
      api_hash: str = ""
      session_string_path: Path = field(
          default_factory=lambda: Path.home() / ".config" / "hestia" / "telegram-voice.session"
      )
      allowed_caller_user_ids: tuple[int, ...] = ()
      half_duplex: bool = True  # ship half-duplex-only; barge-in is opt-in
  ```
- **Modified:** `src/hestia/cli.py` and `src/hestia/commands.py` — new
  command `hestia setup telegram-voice`. Interactive: prompts for phone
  number, runs SMS verification via pyrogram, saves session string to
  `session_string_path` with mode `0o600`. Idempotent: re-running
  regenerates the session.
- **Modified:** `src/hestia/platforms/runners.py` — `run_telegram_voice`
  runner that wires the adapter into the existing platform-runner
  pattern.
- **New:** `tests/unit/test_telegram_voice_config.py` — config rejects
  `enabled=True` with missing `api_id`/`api_hash`/unreadable session
  file.
- **New:** `tests/integration/test_telegram_voice_call_lifecycle.py` —
  mock pyrogram + py-tgcalls; simulate incoming call, accept within
  3 s, drain a few PCM frames into an `asyncio.Queue`, send silence
  back, simulate call-end, assert clean session shutdown and trace
  store record.

**Per-call session state:**

```python
@dataclass
class CallSession:
    call_id: str
    caller_user_id: int
    started_at: datetime
    inbound_pcm_queue: asyncio.Queue[bytes]
    outbound_pcm_queue: asyncio.Queue[bytes]
    hestia_session: Session  # via session_store.get_or_create_session("telegram_voice", str(caller_user_id))
    transcript_count: int = 0
```

**Acceptance for sub-scope A:** Dylan calls the userbot, userbot
accepts within 3 seconds, plays 3 seconds of silence back, hangs up
cleanly. Trace store shows the call record (start time, duration,
caller user_id).

## Sub-scope B — STT + TTS pipeline integration

**Branch (if splitting):** `feature/voice-phase-b-pipeline`

**Files:**

- **Modified:** `src/hestia/adapters/telegram_voice.py` — wire
  `voice.pipeline` (from L41) and the real `voice.vad` (replacing the
  L41 stub).
- **Modified:** `src/hestia/voice/vad.py` — replace the L41 stub with
  Silero-VAD. Async iterator that yields PCM segments bounded by
  voice-activity transitions (silence > 0.5 s ends a segment).
- **Modified:** `pyproject.toml` — add `silero-vad`, `pyrogram`,
  `py-tgcalls` to the `voice` extra (L41 only included whisper +
  piper).
- **New:** `tests/unit/test_silero_vad.py` — feed PCM with known
  silence boundaries, assert correct segmentation.

**Wiring:**

```python
# In TelegramVoiceAdapter._handle_call:
async for speech_segment in vad.segment(call.inbound_pcm_stream()):
    transcript = await pipeline.transcribe(speech_segment)
    # For sub-scope B only: echo back via TTS, no orchestrator yet
    response = f"I heard: {transcript}"
    async for tts_chunk in pipeline.synthesize(response):
        await call.outbound_pcm_queue.put(tts_chunk)
```

**VRAM/CPU coordination:**

- Whisper resident on GPU (loaded once at adapter startup, not per
  turn).
- Piper on CPU (no GPU contention with Qwen).
- Document VRAM headroom in `voice-setup.md` (extends L41 docs).

**Acceptance for sub-scope B:** Call userbot, say "what is the
weather," hear a canned "I heard: what is the weather" response via
TTS within 2 seconds of speech end. No orchestrator intelligence yet.

## Sub-scope C — orchestrator wiring + verbal confirmation + allowed-caller enforcement

**Branch (if splitting):** `feature/voice-phase-b-orchestrator`

**Files:**

- **Modified:** `src/hestia/adapters/telegram_voice.py` — replace the
  echo-back stub from sub-scope B with real orchestrator dispatch.
- **New:** `src/hestia/platforms/voice_confirm.py` — `VoiceConfirmCallback`
  variant of `ConfirmCallback`:
  ```python
  class VoiceConfirmCallback(ConfirmCallback):
      """Verbal confirmation: synthesize 'Should I send this email? Say yes or no'
      and parse the next VAD segment for yes/no/cancel.

      If three consecutive segments can't be parsed, escalate:
      "I didn't catch that — try again or say cancel."
      """
      async def request(self, prompt: str, *, session: Session) -> ConfirmDecision:
          ...
  ```
- **Modified:** `src/hestia/adapters/telegram_voice.py` — half-duplex
  default. While TTS audio is on the outbound queue, pause ingest
  (drop frames, don't transcribe). `half_duplex=False` enables
  barge-in (inbound stays live, TTS aborts on new speech detected).
- **Modified:** `src/hestia/adapters/telegram_voice.py` — allowed-caller
  enforcement on incoming call:
  ```python
  if config.allowed_caller_user_ids:
      if caller_user_id not in config.allowed_caller_user_ids:
          # Reject with a "this Hestia instance doesn't know you" TTS
          # message and hang up. Log to trace store.
          ...
  # else: empty list = dev mode, allow any caller
  ```
- **New:** `docs/adr/ADR-0024-telegram-voice-userbot-model.md` —
  documents the two-account decision (see Architecture above).
- **New:** `tests/integration/test_voice_call_email_with_confirmation.py` —
  end-to-end mock: caller asks Hestia to send an email, Hestia
  verbally requests confirmation, caller says "yes," email goes,
  trace shows the tool call chain.
- **New:** `tests/integration/test_voice_call_unauthorized_caller_rejected.py` —
  caller from un-allowed user_id gets the rejection TTS and call
  hangs up cleanly. Trace store shows the rejection.

**Yes/no parser:**

- Regex first pass: `\b(yes|yeah|yep|sure|okay|ok|do it|go ahead|confirm|affirmative)\b` → yes; `\b(no|nope|nah|cancel|stop|abort|don'?t|negative)\b` → no.
- Fuzzy: lowercase + strip punctuation; if regex misses, fall through
  to a small token list with edit-distance ≤ 1.
- Three consecutive un-parsed segments → escalate prompt.

**Acceptance for sub-scope C:**

- Call userbot, ask to draft and send an email. Hestia asks verbally
  for confirmation. Say "yes." Email is dispatched. Trace shows the
  tool call chain end-to-end.
- Call from an un-allowed phone number: rejected cleanly with the
  TTS message, then hangs up. Trace records the rejection.

---

## Not in scope for Phase B (deferred)

- **Group voice calls.** Private 1:1 only.
- **Video calls.**
- **Call recording.** Transcripts to trace store; raw audio is
  discarded after transcription.
- **Barge-in by default.** Opt-in via `half_duplex=False` only.
  Half-duplex is the safer default — TTS can't get cut off by
  ambient noise.
- **Multi-user concurrent calls.** Single call at a time; second
  incoming call gets "busy" and is rejected cleanly.

## Acceptance for the full L43 arc

- All sub-scope tests pass.
- `mypy src/hestia` → 0 errors.
- `ruff check src/` → ≤ 23.
- ADR-0024 committed.
- `hestia setup telegram-voice` is idempotent and writes the session
  file with mode 0o600.
- Real-world acceptance (Dylan-side, post-merge): husband calls the
  userbot from his phone, asks for the weather or a calendar action,
  hangs up after a natural exchange. Trace store shows it.

## Branch / merge discipline

- Each branch parent: `feature/voice-shared-infra` (sub-scope A) then
  the previous sub-scope branch for B and C.
- Push to `origin/feature/voice-phase-b-*` after each loop's handoff.
- **Do NOT merge to `develop`.** L43 sub-scopes wait for v0.8.1+
  release-prep along with L41 + L42. Release-prep merge order:
  shared-infra → Phase A → Phase B (A → B → C).

## Critical Rules Recap

- §-1: branch from `feature/voice-shared-infra` (sub-scope A) or the
  previous sub-scope (B, C).
- §0: carry-forward = items observed in earlier sub-scopes' reviews
  (Cursor folds these in before launching the next sub-scope).
- One commit per section. ~5-7 commits per sub-scope.
- Final `.kimi-done` with `LOOP=L43a` / `L43b` / `L43c` (or just `L43`
  if Cursor consolidates), `BRANCH=feature/voice-phase-b-*`,
  `COMMIT=<sha>`, `TESTS=<count> passed`, `MYPY_FINAL_ERRORS=0`,
  `RUFF_SRC=<count>`.
- Handoff per sub-scope at `docs/handoffs/L43[a-c]-*-handoff.md`.

## Files in scope (full L43 arc)

- **New:** `src/hestia/adapters/telegram_voice.py`,
  `src/hestia/platforms/voice_confirm.py`,
  `docs/adr/ADR-0024-telegram-voice-userbot-model.md`,
  multiple test files under `tests/unit/` and `tests/integration/`,
  handoff docs.
- **Modified:** `src/hestia/config.py` (`TelegramVoiceConfig`),
  `src/hestia/cli.py` + `src/hestia/commands.py` (`hestia setup
  telegram-voice`), `src/hestia/platforms/runners.py`
  (`run_telegram_voice`), `src/hestia/voice/vad.py` (real Silero
  implementation replacing L41 stub), `pyproject.toml` +
  `uv.lock` (silero-vad, pyrogram, py-tgcalls in `voice` extra),
  `docs/guides/voice-setup.md` (Phase B sections).
