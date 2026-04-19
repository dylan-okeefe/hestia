# Experiment: Telegram voice-message smoke test

**Created:** 2026-04-18
**Type:** Ad-hoc spike (not a Kimi loop)
**Time budget:** 1 afternoon of code, 1 week of use
**Purpose:** Prove or disprove that voice interaction adds real value for Dylan's husband before committing to the 1.5-week L41 real-time voice adapter build.

## Why this exists

L41 is a serious piece of work — userbot setup, phone number provisioning, py-tgcalls integration, Whisper + Kokoro pipelines, VAD, verbal confirmation flow, barge-in handling. Before investing that time, we need a cheap signal on whether voice is actually useful for him in practice, or whether he'll default back to text within two days.

Async voice messages are a close-enough approximation of the real UX to be a valid proxy. If he uses voice messages willingly across a week, real-time calls will be a strict upgrade. If he tries voice messages twice and reverts to text, real-time calls won't save it.

## What to build

A minimal extension to the existing Telegram bot adapter. No new adapter, no new account, no new config beyond a feature flag. Roughly:

1. **Accept voice messages from the existing bot.** Telegram's Bot API delivers voice messages as `.ogg` (opus) files via `Message.voice`. Download, save to a temp file.
2. **Transcribe with faster-whisper** (small or medium model — large is overkill for spike quality). Drop the temp file after.
3. **Feed transcript into the orchestrator** as a normal user turn on the existing Telegram session for that user.
4. **TTS the response** with Piper (fastest, simplest — install is `pip install piper-tts`). Kokoro is better quality but installation is heavier; Piper is fine for the smoke test.
5. **Reply with a voice message** via `send_voice`. Max 1 MB per Telegram's rules — chunk if longer, or truncate with a text fallback.

Approximate file layout:

```
src/hestia/adapters/telegram.py    # existing — extend to handle Message.voice
src/hestia/voice/smoke.py          # new — whisper + piper helpers, delete after L41
```

Gate behind a config flag `telegram.voice_messages: bool` (default False) so the smoke-test code can't break text-only users.

## What NOT to build

- No VAD, no streaming, no VRAM management — single-shot transcribe, single-shot TTS
- No interruption handling
- No verbal confirmation — if the orchestrator wants confirmation, reply with text asking for text confirmation. Voice is input-only for the smoke test.
- No custom voices, no voice selection
- No session continuity across voice/text — treat voice and text as the same Telegram conversation (because they are)
- No error recovery beyond "if transcription or TTS fails, reply with text saying so"

Keep the branch name something like `spike/voice-message-smoke-test` to signal it's not production work. Plan to delete `voice/smoke.py` entirely when L41 lands — the real pipeline in L41b replaces it.

## Success criteria

**Primary signal:** over 7 days of use, does husband *choose* to send voice messages to Hestia when he could have typed?

Track minimally — a single `dogfooding/voice-smoke-log.md` with rows like:

```
2026-04-25 09:12 | voice-in, voice-out | "what's on my calendar" | clean | 4s latency
2026-04-25 09:14 | text-in, text-out   | ... | ... | ...
2026-04-26 07:30 | voice-in, voice-out | "remind me to call mom" | transcription garbled "mom" as "mum" | 6s latency
```

**Pass criteria (go ahead with L41):**
- He sends ≥ 5 voice messages across the week unprompted
- Latency is tolerable — he doesn't complain about it
- Transcription quality is usable — garbled words don't block meaning more than once or twice total

**Fail criteria (kill L41, or at least postpone indefinitely):**
- He sends 0-2 voice messages and stops trying
- He complains explicitly that the latency or quality is worse than typing
- He says "I'd rather just text it"

**Ambiguous signal (keep gathering):**
- 3-4 voice messages, mixed feedback — extend the test by another week before deciding

## Latency expectation for the smoke test

End-to-end for a voice message round-trip, no streaming anywhere:

- Upload voice note to Telegram bot: ~1s
- Download on server: ~500ms
- Whisper small transcribe (5s audio): ~1-2s on GPU
- Orchestrator + LLM response: 2-5s depending on tool use
- Piper TTS generate: ~500ms per sentence
- Upload voice response: ~1s

**Realistic total: 5-10s round trip.** Slower than real-time calls will be, but still usable for async messaging where he's doing something else.

If he tolerates 5-10s round trips on async messages, he will *love* the 1-1.5s first-audio latency on real calls. That's the upgrade curve L41 unlocks.

## Environmental notes

- Piper CPU-only, won't touch VRAM
- Whisper small is ~500 MB VRAM; medium is ~1.5 GB. Plenty of headroom alongside Qwen 9B on a 3060 12GB.
- Voice messages are always ≤ 1 MB per Telegram's limit — if Hestia's TTS output exceeds this, chunk into multiple voice messages or truncate and add a text tail. Keep responses short anyway during the smoke test.

## Decision rubric for Dylan

After 7 days, write the outcome into `docs/development-process/kimi-loop-log.md` under a new dated entry. Three possible outcomes:

**Outcome A — Go.** Voice is useful. Write full L41a/b/c specs in `docs/development-process/kimi-loops/`, point `KIMI_CURRENT` at L41a, proceed with Stage G.

**Outcome B — No-go.** Voice didn't click. Leave L41 in the plan as a "future" item. Repurpose the 1.5 weeks for whichever backlog item from L40's triage is hungriest. Keep the smoke-test branch alive on a shelf — async voice messages are still useful even if the full build doesn't ship.

**Outcome C — Revise.** Signal is positive but the friction is in specific places (transcription quality, or TTS voice quality, or specific commands not working well via voice). Narrow L41 scope to fix those specific problems first, then reassess. Example: maybe he'd love voice-in with text-out, and TTS never matters. That's a much smaller build.

## What happens to this doc

Delete once L41 ships (or doesn't). It's a temporary gate, not a permanent spec. The outcome gets immortalized in `kimi-loop-log.md`; the experiment itself can leave.
