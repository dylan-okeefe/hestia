# ADR-0026: Discord Always-Listening Voice Channel

**Status:** Accepted  
**Date:** 2026-04-20  
**Deciders:** Dylan O'Keefe, Cursor (build orchestrator)  

## Context

Hestia needs a hands-free voice interface so Dylan's husband can interact with the assistant while doing chores (cooking, laundry) without pulling out a phone. The target UX is comparable to ChatGPT Voice or Siri: always-listening, natural turn-taking, responds via TTS.

### Options considered

| Option | Pros | Cons |
|--------|------|------|
| **Telegram userbot (pyrogram + py-tgcalls)** | Native phone-call UX | Requires dedicated phone number + SIM; Telegram ToS grey-area for userbots; two-account model breaks inline-keyboard confirmations |
| **Matrix/Element WebRTC** | Local-first, no third party | matrix-nio has no voice support; aiortc integration is a 5-10× project; no hands-free activation |
| **Self-hosted WebRTC PWA** | Full control | Defeats hands-free UX (no Siri-style activation); extra client software for husband |
| **Discord voice channel** | No phone number; bot auth only; native multi-user via user_id; clean full-duplex; py-cord has voice receive | Third-party audio transit; husband needs Discord account |

## Decision

Use **Discord** as the Phase B voice channel. Hestia sits permanently in a dedicated voice channel on Dylan's private server. The bot joins on startup and stays connected indefinitely.

### Why Discord over Telegram userbot

- **No hardware prereqs.** Bot auth is a token from the Discord Developer Portal. No phone number, no SIM, no session strings.
- **No two-account model.** The existing Telegram bot (`@HestiaBot`) continues handling text and Phase A voice messages. Discord is a new, parallel adapter.
- **Native multi-user.** Discord's voice protocol tags every RTP stream with the speaker's `user_id`. Once v0.8.1 multi-user scoping landed, memory and trust decisions naturally scope per-speaker without extra adapter plumbing.
- **Full-duplex is natural.** Unlike a phone call, Discord's voice architecture doesn't force half-duplex. Barge-in ships on by default.

### Why Discord over Matrix/Element or self-hosted WebRTC

Matrix voice via WebRTC is technically cleaner for a local-first ethos, but matrix-nio has no voice support and `aiortc` integration would be a separate multi-week effort. Self-hosted WebRTC PWA defeats the hands-free Siri-style UX because it requires a dedicated client app. Discord is the fastest path to an AirPods-friendly experience; Matrix remains a future adapter.

### Why py-cord over discord.py

discord.py removed voice *receive* support years ago. py-cord (pycord) is the community-maintained drop-in fork that adds voice receive back. It supplants discord.py in the same import namespace, so we use `py-cord[voice]` instead of `discord.py`.

## Architecture

### Audio flow

```
Discord RTP stream (48 kHz stereo Opus)
    ↓
py-cord Sink (decodes to PCM)
    ↓
TranscriptionSink (buffers per user, flushes after silence)
    ↓
audioop: stereo → mono → 16 kHz resample
    ↓
faster-whisper (STT)
    ↓
HeuristicTurnDetector (punctuation + silence thresholds)
    ↓
Orchestrator.process_turn()
    ↓
piper-tts (TTS)
    ↓
audioop: mono 22.05 kHz → stereo 48 kHz resample
    ↓
QueueAudioSource → VoiceClient.play()
    ↓
Discord voice channel
```

### Turn detection

Phase B ships a **heuristic turn detector** (rule-based: punctuation + keyword + silence thresholds). A neural turn-detector (Pipecat Smart Turn v3, LiveKit Turn Detector, etc.) can be dropped in later by implementing the same `predict(partial_transcript, silence_ms) -> float` interface.

Default thresholds:
- **Fast path:** 350 ms silence + transcript ends with `.?!` → commit
- **Patient path:** up to 4 s silence without punctuation → commit
- **Safety timeout:** 6 s silence regardless → commit
- **Filler words:** `uh`, `um`, `wait`, etc. at tail → extend patience
- **Keyword endpointing:** optional (`("over",)`) for CB-radio mode

### Barge-in

Inbound VAD stays live during TTS playback. Detected speech from any user stops current playback (`VoiceClient.stop()`), flushes the outbound queue, and starts a new listen cycle. The user's speech is treated as a **new turn** (not spliced into the previous transcript).

### Multi-user scoping

Each speaker gets a separate `SpeakerSession` keyed on their Discord `user_id`. Sessions map to Hestia orchestrator sessions with `platform="discord"`, `platform_user=str(discord_user_id)`. Memory, trust, and style profiles scope per-speaker automatically via the existing L45a identity plumbing.

### Verbal confirmation

Destructive tools (`terminal`, `write_file`, `email_send`) trigger a verbal confirmation prompt: "Should I send this email? Say yes or no." The next VAD segment is parsed with regex + fuzzy match for yes/no. Three consecutive unparsable segments escalate to "I didn't catch that — say yes, no, or cancel." If a paired text channel is configured, an inline-button fallback is posted there (either click-or-voice completes it).

## Consequences

### Positive

- Fastest path to a working hands-free voice UX.
- No hardware prereqs (phone number, SIM).
- Multi-user is free due to Discord's per-speaker RTP tagging.
- Full-duplex barge-in works out of the box.

### Negative / Risks

- **Third-party audio transit.** Audio flows through Discord's servers. Mitigation: private server, bot token hygiene.
- **Husband needs Discord account.** Mitigation: onboarding doc with mobile Discord + AirPods setup instructions.
- **py-cord dependency.** Community fork; if maintenance stops, may need to vendor or migrate.
- **No end-to-end encryption.** Discord voice is encrypted Discord→client but not client→client E2E. Acceptable for a personal assistant on a private server.

### Revisit trigger

Reconsider if:
- VRAM headroom tightens (whisper + Qwen 9B + smart-turn model exceeds RTX 3060 12 GB).
- Matrix voice becomes feasible with significantly less effort.
- Discord policy changes affect bot voice receive.

## Related

- `docs/development-process/prompts/v0.8.0-release-and-voice-launch.md` — Phase B launch plan
- `docs/guides/voice-setup.md` — Voice installation and VRAM budget guidance
- `src/hestia/platforms/discord_voice_runner.py` — Implementation
- `src/hestia/voice/turn_detector.py` — Turn-detection interface
