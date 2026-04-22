---
name: hestia-voice
description: Discord voice-channel development for Hestia. Use when modifying, debugging, or extending the voice pipeline (STT, TTS, turn detection, DAVE encryption, audio resampling).
---

# Hestia Voice Development

Discord voice-channel listener implementing Phase B sub-scopes A–C. Joins voice,
records per-speaker PCM, transcribes via faster-whisper, detects turns, dispatches
through the orchestrator, and streams TTS responses back.

## Architecture

```
Discord Voice Channel
  ↓ (Opus over UDP, DAVE-encrypted)
py-cord PacketRouter
  ↓ (VoiceData objects with .pcm)
TranscriptionSink.write()
  ↓ (48kHz stereo PCM)
_tomono() + _ratecv() → 16kHz mono
  ↓
SpeakerSession._accumulated_audio
  ↓ (timer fires after fast_silence_ms)
check_turn() → pipeline.transcribe()
  ↓ (turn detector decides)
_commit_turn() → orchestrator.process_turn()
  ↓
_speak() → pipeline.synthesize()
  ↓ (22050 Hz mono PCM)
_ratecv() + _tostereo() → 48kHz stereo
  ↓
_QueueAudioSource → voice_client.play()
  ↓ (DAVE-encrypted Opus)
Discord Voice Channel
```

## Critical files

| File | Role |
| --- | --- |
| `src/hestia/platforms/discord_voice_runner.py` | Main voice runner: event loop patch, SpeakerSession, TranscriptionSink, _QueueAudioSource |
| `src/hestia/voice/pipeline.py` | Lazy-loading STT/TTS pipeline: WhisperModel + PiperVoice |
| `src/hestia/voice/turn_detector.py` | HeuristicTurnDetector: punctuation, silence, filler-word, keyword heuristics |
| `src/hestia/config.py` | VoiceConfig + DiscordVoiceConfig dataclasses |
| `config.runtime.py` | Runtime overrides (stt_model, stt_language, etc.) |

## DAVE E2EE (non-negotiable)

Discord globally enforces DAVE. Without it, voice connection gets 4017.

**Required dependency:**
```toml
py-cord[voice] @ git+https://github.com/Pycord-Development/pycord.git@42cd1b4a737ff7d7a5070442fd1d26c701072794
davey>=0.1.5
```

**Branch status:** `fix/voice-rec-2` is 18 commits ahead of master in voice
receive (PR #3159) but 26 commits behind in general fixes. Master has DAVE send
(PR #3143) but not receive. Once PR #3159 merges, migrate to stable py-cord.

**Known upstream issues:**
- `transition_id == 0` skips sending `dave_transition_ready`, stalling audio.
  Runtime-patched in installed site-packages.
- Intermittent `CryptoError: Decryption failed` during key rotation. Drops
  packets but does not crash the bot.

## Event loop mismatch (DAVE branch)

The DAVE branch caches `asyncio.get_event_loop()` at `Client` init, but
`asyncio.run()` creates a fresh loop. Without this patch, voice tasks raise
`RuntimeError`.

```python
_running_loop = asyncio.get_running_loop()
bot.loop = _running_loop
bot._connection.loop = _running_loop
```

This must happen **before** `ch.connect()`.

## Sink API compatibility

The DAVE branch passes `VoiceData` objects instead of raw `bytes`:

```python
def write(self, data, user):
    if hasattr(data, "pcm"):
        pcm = data.pcm
        user = int(getattr(data.source, "id", user))
    else:
        pcm = data
    # ... buffer pcm
```

Code must handle both APIs for forward compatibility.

## Audio resampling (Python 3.13, no audioop)

`audioop` was removed in Python 3.13. Use numpy-based replacements:

```python
def _tomono(stereo_bytes: bytes, width: int, lfactor: float, rfactor: float) -> bytes:
    dtype = np.int16 if width == 2 else np.int8
    arr = np.frombuffer(stereo_bytes, dtype=dtype)
    left = arr[0::2] * lfactor
    right = arr[1::2] * rfactor
    mono = (left + right).astype(dtype)
    return mono.tobytes()

def _ratecv(data: bytes, width: int, nchannels: int, inrate: int, outrate: int, state: Any) -> tuple[bytes, Any]:
    dtype = np.int16 if width == 2 else np.int8
    arr = np.frombuffer(data, dtype=dtype).reshape(-1, nchannels)
    old_len = arr.shape[0]
    new_len = int(old_len * outrate / inrate)
    if new_len == 0:
        return b"", None
    old_x = np.linspace(0, old_len - 1, old_len)
    new_x = np.linspace(0, old_len - 1, new_len)
    resampled = np.empty((new_len, nchannels), dtype=dtype)
    for ch in range(nchannels):
        resampled[:, ch] = np.interp(new_x, old_x, arr[:, ch].astype(np.float32)).astype(dtype)
    return resampled.tobytes(), None
```

## TTS pipeline

Piper outputs 22050 Hz mono PCM16. Must resample to 48kHz stereo for Discord:

```python
discord_pcm = _resample_for_discord(chunk, _PIPER_SAMPLE_RATE)  # 22050 → 48000 stereo
```

**Drain loop (critical):** Do not cut off TTS with a fixed sleep. Wait for the
queue to empty and playback to stop:

```python
source.finish()
for _ in range(300):
    if source._q.empty() and not voice_client.is_playing():
        break
    await asyncio.sleep(0.1)
```

## Common bugs and fixes

### 1. Self-cancellation in `_commit_turn()`
**Symptom:** Turn commits but no LLM/TTS activity. No error log.
**Cause:** `_commit_turn()` calls `self._patience_task.cancel()`. When called
from `_patience_commit()`, this cancels the current task. `CancelledError` is
delivered at the next `await` inside `_commit_turn()`, silently aborting it.
**Fix:** Only cancel if the patience task is a *different* task:
```python
current_task = asyncio.current_task()
if self._patience_task is not None and self._patience_task is not current_task:
    self._patience_task.cancel()
    self._patience_task = None
elif self._patience_task is current_task:
    self._patience_task = None
```

### 2. Concurrent `check_turn()` causing double commits
**Symptom:** Two rapid-fire TTS responses for one utterance.
**Cause:** `Semaphore(2)` allows two `check_turn()` tasks to run concurrently.
The first commits and clears `_accumulated_audio`; the second is mid-STT and
commits its stale result.
**Fix:** Replace `Semaphore(2)` with `asyncio.Lock()` and add a `_committing`
flag that makes subsequent `check_turn()` calls return early.

### 3. TTS audio cutoff
**Symptom:** Response cuts off after first sentence or mid-word.
**Cause:** Hard `await asyncio.sleep(0.5)` after synthesis does not wait for
py-cord's player thread to drain.
**Fix:** Polling drain loop (see TTS pipeline section above).

### 4. Whisper hallucinations on short audio
**Symptom:** User says "Can you hear me?", transcript is "Thank you." or "You".
**Cause:** `medium` model is unreliable on <0.5s fragments. Discord's noise gate
or packet loss may also shorten captured audio.
**Fix:** Add `min_commit_audio_ms` guard (default 500ms). If audio is shorter,
schedule patience instead of committing. Also try:
- `stt_language="en"` to skip language auto-detection
- `condition_on_previous_text=False` to prevent chaining
- Upgrading to `large-v2` or `large-v3-turbo` (needs more VRAM)

### 5. Aggressive flush timer splitting phrases
**Symptom:** One sentence produces multiple turns.
**Cause:** `fast_silence_ms` default was 350ms. Jitter gaps between words reset
the timer, causing premature flushes.
**Fix:** Raise to 800ms (or higher for noisy connections).

## Debugging tips

1. **Enable INFO logging** — The voice runner now logs every step:
   ```
   _commit_turn: resolving session → resolved → calling orchestrator
   _commit_turn: orchestrator done parts=N response=...
   _speak: starting → calling voice_client.play → synthesized N chunks → finished
   ```
2. **Check audio duration** — faster-whisper logs `Processing audio with duration`.
   If this is <50% of expected utterance length, the issue is capture quality,
   not STT model.
3. **Check Opus packet loss** — `discord.opus WARNING N packets were lost`.
   Persistent loss means network or Discord client issues.
4. **Verify DAVE state** — `Preparing to upgrade to a DAVE connection` should be
   followed by successful audio flow. If decryption errors appear, DAVE keys may
   be out of sync.
5. **Test TTS in isolation** — If STT is unreliable, mute yourself in Discord
   and test TTS by sending a text command that triggers `_speak()` directly.

## Dependencies

```toml
[project.optional-dependencies]
voice = [
    "faster-whisper>=1.0.0",
    "piper-tts>=1.2.0",
    "py-cord[voice] @ git+https://github.com/Pycord-Development/pycord.git@42cd1b4a737ff7d7a5070442fd1d26c701072794",
    "davey>=0.1.5",
]
```

**Note:** `py-cord` must be the exact git commit until PR #3159 merges to master.
Do not upgrade to a PyPI release without verifying DAVE receive support.
