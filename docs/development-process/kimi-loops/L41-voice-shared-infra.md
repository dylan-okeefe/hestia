# L41 — Voice adapter: shared infrastructure (STT/TTS pipeline + config + extras)

**Status:** Spec only. **Do not merge to `develop`.** Per the
post-release merge discipline rule in `.cursorrules`, this branch lives
on `origin/feature/voice-shared-infra` until a v0.8.1+ release-prep doc
names it in scope.

**Branch:** `feature/voice-shared-infra` (forks from `develop` at the
v0.8.0 tag — `b1e81ae`).

**Purpose:** Land the audio plumbing both voice phases (Phase A —
Telegram voice messages; Phase B — Telegram voice calls) depend on.
This loop ships *zero user-facing behavior change*. Hestia without
`pip install hestia[voice]` continues exactly as before. With the
extra installed, the pipeline is importable and unit-tested but no
adapter calls into it yet — that's L42 / L43.

**Why "shared infra" gets its own loop instead of folding into Phase A:**
Both phases use the same STT and TTS code paths. Splitting the audio
pipeline now means Phase A and Phase B branches don't both need to
contain the same setup work, and the pipeline can land/be reviewed
independently of Telegram-specific glue.

---

## Section 1 — `src/hestia/voice/pipeline.py` (new module)

Transport-agnostic audio pipeline. The *only* `hestia.voice.*` consumer
right now will be Phase A's voice-message handler; Phase B will plug in
the same singleton.

**Class shape (sketch — exact API is Cursor's call):**

```python
@dataclass
class VoicePipeline:
    config: VoiceConfig
    _whisper_model: faster_whisper.WhisperModel | None = None
    _tts_engine: PiperVoice | None = None  # or KokoroPipeline
    _init_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def transcribe(self, pcm_bytes: bytes, *, sample_rate: int = 16000) -> str:
        await self._ensure_stt_loaded()
        # faster-whisper transcribe; return text
        ...

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        """Stream TTS audio chunks (sentence-level granularity)."""
        await self._ensure_tts_loaded()
        # split text into sentences, yield audio for each
        ...

    async def _ensure_stt_loaded(self) -> None:
        async with self._init_lock:
            if self._whisper_model is None:
                self._whisper_model = await asyncio.to_thread(
                    faster_whisper.WhisperModel,
                    self.config.stt_model,
                    device=self.config.stt_device,
                    compute_type=self.config.stt_compute_type,
                    download_root=str(self.config.model_cache_dir),
                )

    async def _ensure_tts_loaded(self) -> None: ...


_PIPELINE: VoicePipeline | None = None
_PIPELINE_LOCK = asyncio.Lock()


async def get_voice_pipeline(config: VoiceConfig | None = None) -> VoicePipeline:
    """Process-wide singleton. Lazy first-init under a lock."""
    global _PIPELINE
    async with _PIPELINE_LOCK:
        if _PIPELINE is None:
            if config is None:
                raise RuntimeError("First call must pass a VoiceConfig")
            _PIPELINE = VoicePipeline(config=config)
    return _PIPELINE
```

**Key behaviors:**

- **Lazy model load.** Importing `hestia.voice.pipeline` must NOT
  download or load any models. Models load on first `transcribe()` /
  `synthesize()` call. This keeps `hestia version` and `hestia doctor`
  fast even when `[voice]` is installed.
- **Singleton accessor.** Whisper and Piper are 1.6 GB and ~30 MB
  resident respectively; loading them per-call would defeat the point.
- **Thread-safe init.** Use `asyncio.Lock` for the init guard. The
  underlying model load via `asyncio.to_thread` to avoid blocking the
  event loop.
- **Sentence split for TTS.** Naive split on `. `, `! `, `? ` is fine
  for v1; Phase B may want a smarter splitter for natural prosody. Keep
  it pluggable.

**Imports gated.** `import faster_whisper` and `import piper`
inside the methods (or at module top with try/except → raise
`MissingExtraError("Install hestia[voice]")`). Hestia core must not
hard-depend on these.

## Section 2 — `src/hestia/voice/vad.py` (new module, stub-acceptable)

```python
class SileroVAD:
    """Silero-VAD wrapper. Stub in L41 (returns the whole input as one segment).

    Phase B (L43) replaces the stub with the real VAD that segments
    by voice-activity boundaries.
    """

    async def segment(self, pcm_stream: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
        # Stub: yield the full stream as one segment
        buffer = b""
        async for chunk in pcm_stream:
            buffer += chunk
        if buffer:
            yield buffer
```

Phase A doesn't need VAD (voice messages arrive pre-bounded by
Telegram). The stub keeps the module importable so Phase B has
something to extend without scope creep.

## Section 3 — `src/hestia/config.py` additions

```python
@dataclass
class VoiceConfig:
    stt_model: str = "faster-whisper/large-v3-turbo"  # or "medium", "small"
    stt_device: str = "cuda"  # "cpu" fallback
    stt_compute_type: str = "int8"  # int8 | float16 | float32
    tts_engine: str = "piper"  # "piper" | "kokoro"
    tts_voice: str = "en_US-amy-medium"
    tts_speed: float = 1.0
    model_cache_dir: Path = field(
        default_factory=lambda: Path.home() / ".cache" / "hestia" / "voice"
    )


@dataclass
class HestiaConfig:
    # ... existing fields ...
    voice: VoiceConfig = field(default_factory=VoiceConfig)
```

`TelegramConfig.voice_messages: bool = False` — added in L42, not L41
(scope discipline: only land the config field with the consumer).

## Section 4 — `pyproject.toml` `voice` extra

Add to `[project.optional-dependencies]`:

```toml
voice = [
    "faster-whisper>=1.0.0",
    "piper-tts>=1.2.0",
]
```

(Kokoro and Silero-VAD added in L43 if Phase B picks them up.)

Run `uv lock` to refresh `uv.lock`. Verify `pip install -e .[voice]`
resolves in a clean venv. Hestia core install (`pip install -e .`) must
remain unchanged in resolved deps.

## Section 5 — `docs/guides/voice-setup.md` (new)

Concise setup guide:

1. **Install the extra:** `pip install hestia[voice]` or
   `uv sync --extra voice`.
2. **Model auto-download.** First `transcribe()` call downloads
   ~1.6 GB of faster-whisper weights to
   `~/.cache/hestia/voice/`. Override path via
   `VoiceConfig.model_cache_dir`.
3. **Piper voices.** Document downloading
   `en_US-amy-medium.onnx` + `en_US-amy-medium.onnx.json` from the
   Piper voice gallery (link). Place in `model_cache_dir`.
4. **VRAM budget on a 3060 12GB alongside Qwen 9B Q4_K_M:**
   ~5.5 GB Qwen + ~1.6 GB Whisper int8 + 0 GB Piper (CPU) =
   ~7.1 GB used, ~4.9 GB headroom for KV cache and activations.
5. **`hestia doctor voice-prerequisites`** — calls
   `from hestia.voice.pipeline import get_voice_pipeline`; reports
   "voice extra not installed" cleanly if `faster_whisper` import
   fails. (Implement in this loop or punt to L42 — Cursor's call;
   prefer landing the doctor check here so users have feedback before
   any adapter touches the pipeline.)

## Section 6 — Tests

**`tests/unit/test_voice_pipeline.py` (new):**

- `test_transcribe_lazy_loads_model` — patch `faster_whisper.WhisperModel`,
  call `transcribe(b"...")` once, assert init was called exactly once;
  call again, assert init was NOT called again.
- `test_synthesize_yields_sentence_chunks` — patch piper, feed
  `"First sentence. Second sentence."`, assert two audio chunks
  yielded.
- `test_singleton_returns_same_instance` — call `get_voice_pipeline`
  twice, assert same object.
- `test_singleton_first_call_requires_config` — call
  `get_voice_pipeline()` with no config and assert `RuntimeError`.
- `test_import_without_extra` — verify `hestia.voice.pipeline` is
  importable even if `faster_whisper` is missing (the import-error
  path triggers only on first model load).

**Mocking strategy:** Stub `faster_whisper.WhisperModel` and
`piper.PiperVoice` (or whichever the chosen TTS class is) to avoid
needing the actual extras installed in CI. Run the test file with the
extras absent to verify the import-time-safe contract.

## Section 7 — Handoff + version bump

- `pyproject.toml`: bump dev version (e.g. `0.8.0` → `0.8.1.dev0`).
  This is the post-v0.8.0 dev marker; it does NOT signal release intent
  (per the merge-discipline rule, the next release prep is what
  triggers a real v0.8.1).
- `uv.lock`: regenerate.
- `docs/handoffs/L41-voice-shared-infra-handoff.md`: ~30-40 lines.
  Cover: what shipped, mocks/test strategy, VRAM headroom check, what
  L42 and L43 will plug into.

---

## Acceptance

- `from hestia.voice.pipeline import get_voice_pipeline, VoicePipeline`
  works without `[voice]` extra installed.
- `pip install -e .[voice]` resolves cleanly in a fresh venv.
- All new unit tests pass.
- Existing test count unchanged for everything outside
  `tests/unit/test_voice_pipeline.py` and the new doctor check.
- `mypy src/hestia` → 0 errors.
- `ruff check src/` → ≤ 23 (no new debt).
- `hestia doctor` runs without error whether `[voice]` is installed
  or not.

## Branch / merge discipline

- Branch from `v0.8.0` tag (`b1e81ae` on develop history).
- Push to `origin/feature/voice-shared-infra` after handoff.
- **Do NOT merge to `develop`.**
- L42 and L43 fork from this branch, not from `develop`. Future
  release-prep doc merges this branch first, then L42/L43 in order.

## Files in scope

- **New:** `src/hestia/voice/__init__.py`, `src/hestia/voice/pipeline.py`,
  `src/hestia/voice/vad.py`, `docs/guides/voice-setup.md`,
  `tests/unit/test_voice_pipeline.py`
- **Modified:** `src/hestia/config.py` (add `VoiceConfig`),
  `pyproject.toml` (add `voice` extra + dev version bump),
  `uv.lock` (regen), optionally `src/hestia/doctor.py` (add
  voice prereq check).

## Critical Rules Recap

- §-1: branch from v0.8.0 tag (`b1e81ae`). Do NOT merge previous phase
  to develop.
- §0: no carry-forward — first loop in the voice arc.
- One commit per logical section: pipeline.py, vad.py + config,
  pyproject.toml + voice-setup.md, tests, handoff. ~5 commits total.
- Final `.kimi-done` with `LOOP=L41`, `BRANCH=feature/voice-shared-infra`,
  `COMMIT=<sha>`, `TESTS=<count> passed`, `MYPY_FINAL_ERRORS=0`,
  `RUFF_SRC=<count>`.
