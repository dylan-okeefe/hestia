# L42 — Voice Phase A: Telegram voice messages via existing bot

**Status:** Spec only. **Do not merge to `develop`** — branch lives on
`origin/feature/voice-phase-a-messages` until release-prep names it.

**Branch:** `feature/voice-phase-a-messages` — **forks from
`feature/voice-shared-infra`** (NOT from `develop`). The shared
pipeline must exist on disk before this loop can land.

**Depends on:** L41 (`feature/voice-shared-infra`) — must be at least
on `origin` and `feature/voice-shared-infra` checked out as the parent
branch.

**Purpose:** Husband can record a voice message in Telegram, send it to
the existing `@HestiaBot`, and get a voice-message reply within ~15s.
This is the "lightweight stepping stone" that delivers user-visible
voice UX while Phase B (live calls) is built. Same STT/TTS code; no
real-time concerns.

---

## Section 1 — `src/hestia/adapters/telegram.py` voice handler

Extend the existing bot adapter (do NOT create a new adapter). Catch
`Message.voice` events alongside the existing `Message.text` handler.

**Sketch:**

```python
async def _handle_voice_message(self, message: Message) -> None:
    if not self._cfg.voice_messages:
        # Feature flag off — silently ignore (the less annoying option
        # vs replying "voice messages disabled" every time)
        logger.debug("Voice message ignored (telegram.voice_messages=False)")
        return

    pipeline = await get_voice_pipeline(self._app.config.voice)

    # 1. Download the .ogg file
    voice_file = await message.voice.get_file()
    with tempfile.NamedTemporaryFile(suffix=".ogg") as ogg:
        await voice_file.download_to_drive(ogg.name)

        # 2. Convert .ogg/opus to PCM 16kHz mono via ffmpeg
        pcm_bytes = await self._ogg_to_pcm(ogg.name, sample_rate=16000)

    # 3. Transcribe
    transcript = await pipeline.transcribe(pcm_bytes, sample_rate=16000)

    # 4. Feed to orchestrator as a normal text turn
    response_text = await self._app.orchestrator.process_turn(
        session=session, user_message=transcript
    )

    # 5. Synthesize → assemble .ogg/opus ≤ 1MB
    audio_chunks: list[bytes] = []
    async for chunk in pipeline.synthesize(response_text):
        audio_chunks.append(chunk)

    full_audio_ogg = await self._pcm_chunks_to_ogg_opus(audio_chunks)

    # 6. Telegram voice note limit handling
    if len(full_audio_ogg) > 1_000_000:
        truncated_ogg = await self._truncate_ogg_to_size(full_audio_ogg, 1_000_000)
        await message.reply_voice(voice=truncated_ogg)
        await message.reply_text(
            "(Voice reply truncated to fit Telegram's 1MB limit. "
            "Full text:)\n\n" + response_text
        )
    else:
        await message.reply_voice(voice=full_audio_ogg)
```

**Key concerns:**

- **`ffmpeg` dependency.** Telegram voice notes are .ogg/opus.
  Whisper wants PCM 16kHz mono. ffmpeg is the standard converter;
  `pydub` wraps it but `pydub` itself isn't a hard dep — call ffmpeg
  via `asyncio.subprocess` directly. Document the system `ffmpeg`
  requirement in `docs/guides/voice-setup.md` (extends L41's setup).
- **Telegram voice note 1 MB limit.** This is per the Bot API. For
  long replies, truncate audio + send rest as text. Do not silently
  drop content.
- **Session selection.** Voice messages route through
  `get_or_create_session("telegram", str(message.from_user.id))` —
  the same path text messages use. (The L41 hotfix made this race-safe;
  no special handling.)
- **Confirmation flow.** Voice messages do NOT change confirmation
  UX. Destructive tools still pop the existing inline-keyboard
  confirmation (L23). Verbal confirmations are Phase B only — Phase A
  users get the inline keyboard alongside their voice reply.

## Section 2 — `src/hestia/config.py` flag

```python
@dataclass
class TelegramConfig:
    # ... existing fields ...
    voice_messages: bool = False  # Phase A feature flag
```

Default `False` so existing users get no behavior change after the
L42 branch eventually merges (which won't happen in L42 itself — see
merge discipline below).

## Section 3 — Tests

**`tests/integration/test_telegram_voice_message.py` (new):**

- Mock `python-telegram-bot`'s `Application` and the `Message.voice`
  / `voice.get_file` chain.
- Mock `get_voice_pipeline()` → return a stub with
  `transcribe(...) -> "what is the weather"` and `synthesize(...)`
  yielding two PCM chunks.
- Mock `ffmpeg` subprocess via patching `asyncio.create_subprocess_exec`.
- Feed a fixture `.ogg` (or just bytes — the stub doesn't actually
  decode); assert:
  - The orchestrator received the right transcript.
  - `message.reply_voice` was called.
  - The truncate-and-text-fallback path triggers when the synthesized
    audio exceeds 1 MB.
- `test_voice_message_disabled_when_flag_false` — pipeline never
  invoked.

**`tests/unit/test_telegram_adapter_voice_routing.py` (new, smaller):**

- Asserts `_handle_voice_message` is registered on the dispatcher when
  `voice_messages=True`.
- Asserts it's NOT registered when `voice_messages=False`. (Or: it IS
  registered but no-ops; depends on Cursor's chosen pattern. Pick one
  and test it.)

**Fixture audio:** Optional. A 1-second silent .ogg encoded with
opus is enough for any non-mocked path. Place at
`tests/fixtures/voice/silence-1s.ogg` if needed.

## Section 4 — Documentation

Append to `docs/guides/voice-setup.md` (created in L41):

- New section: **Enabling voice messages on Telegram.** Set
  `telegram.voice_messages = True` in config. Restart the bot.
  Document the system `ffmpeg` requirement.
- Note that voice messages reuse the existing `TelegramConfig.bot_token`
  — no extra credentials.
- Cross-reference Phase B for live-call UX.

## Section 5 — Cleanup

Delete `docs/experiments/telegram-voice-smoke-test.md` — that doc
shipped in v0.8.0 as a planning artifact and Phase A subsumes it.
(Per the launch plan: "After v0.8.0 is public, delete
docs/experiments/telegram-voice-smoke-test.md — Phase A subsumes it.")

## Section 6 — Handoff

`docs/handoffs/L42-voice-phase-a-messages-handoff.md` — ~40 lines.
Cover end-to-end flow with the mock paths, ffmpeg system dep, the
1MB-truncation behavior, and Dylan's "husband sends a voice asking
about the weather, gets one back in <15s" success metric.

---

## Acceptance

- All new tests pass.
- Existing tests unchanged.
- `mypy src/hestia` → 0 errors.
- `ruff check src/` → ≤ 23.
- Default `voice_messages=False` means no behavior change for users
  not opting in.
- With `voice_messages=True` and `[voice]` extra installed,
  end-to-end mock test demonstrates the full pipeline.

## Success metric (Dylan-defined; evaluated post-merge)

- Husband sends a voice message asking about the weather, gets a voice
  message back, in under 15 seconds end-to-end.
- Transcription quality is good enough that "mom" isn't consistently
  heard as "mum."
- TTS is clear enough to understand over AirPods in a noisy room.

This metric is evaluated by Dylan after the branch eventually merges
to develop (post-release-prep), not as part of L42 acceptance.

## Branch / merge discipline

- Branch parent: `feature/voice-shared-infra` (NOT `develop`).
- Push to `origin/feature/voice-phase-a-messages` after handoff.
- **Do NOT merge to `develop`.** L42 sits on `origin` until a v0.8.1+
  release-prep doc names both `feature/voice-shared-infra` and
  `feature/voice-phase-a-messages` in scope. The release-prep merge
  order will be: shared-infra first, then Phase A on top.

## Files in scope

- **Modified:** `src/hestia/adapters/telegram.py` (voice handler),
  `src/hestia/config.py` (`TelegramConfig.voice_messages`),
  `docs/guides/voice-setup.md` (Phase A section).
- **New:** `tests/integration/test_telegram_voice_message.py`,
  `tests/unit/test_telegram_adapter_voice_routing.py`,
  optionally `tests/fixtures/voice/silence-1s.ogg`,
  `docs/handoffs/L42-voice-phase-a-messages-handoff.md`.
- **Deleted:** `docs/experiments/telegram-voice-smoke-test.md`.

## Critical Rules Recap

- §-1: branch from `feature/voice-shared-infra`, NOT develop.
- §0: carry-forward = nothing (first Phase A loop).
- One commit per section. ~5 commits.
- Final `.kimi-done` with `LOOP=L42`, `BRANCH=feature/voice-phase-a-messages`,
  `COMMIT=<sha>`, `TESTS=<count> passed`, `MYPY_FINAL_ERRORS=0`,
  `RUFF_SRC=<count>`.
