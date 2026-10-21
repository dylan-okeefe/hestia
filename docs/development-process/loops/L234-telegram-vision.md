# L234 — Vision pipeline: Telegram photos → Strata (Flash-Next multimodal)

Card: TaskView #71 (Dylan-approved architecture: native inline vision, NOT a
describe-image subagent — see card note). Follow-up to L232 (inference backend
profiles).

## Context

- Strata at http://127.0.0.1:8080/v1 is LIVE and FROZEN: OpenAI-compatible,
  model `qwen3.8-flash-next-iq3_s`, `input_modalities: ["text","image"]`. Vision
  is already loaded — no restart/reconfig of Strata, ever.
- Hestia has NO image path today: no PHOTO handler in
  `src/hestia/platforms/telegram_adapter.py` (photos are silently dropped — a
  UX bug this loop also fixes), `_on_message` carries text only, no image
  content blocks in the inference client (L232 `server_type="openai-compat"`).
- Ornith (llama.cpp backend) has NO vision mmproj — images must never be sent
  to a `llamacpp` server_type; strip with a logged warning.
- ffmpeg is already a Hestia dependency (voice pipeline, telegram_adapter
  ~:1144-1270) — use it for downscale/re-encode; add NO new dependencies.
- Production runtime config: `/home/dylan/Hestia-runtime/config.runtime.py`
  (untracked; telegram section built in `_telegram_from_env()`).

## §1 — Config

`TelegramConfig` (src/hestia/config.py, env prefix TELEGRAM):
- `vision: bool = False` — master switch, default OFF.
- `vision_max_images_per_message: int = 4`
- `vision_max_edge_px: int = 1024`
Gating rule (enforced where the request is built): images flow ONLY when
`telegram.vision` is True AND `inference.server_type == "openai-compat"`.
If vision=True with server_type="llamacpp": startup WARNING log + images
stripped per-request with a warning (never sent to Ornith).

## §2 — Telegram adapter

1. Register `MessageHandler(filters.PHOTO & ~filters.COMMAND, self._handle_photo)`
   in `start()` next to the existing handlers.
2. `_handle_photo`: collect `update.effective_message.photo` (list of
   PhotoSize), take the largest, download via `update.effective_message.photo[-1].get_file()`
   (httpx download like `_handle_voice_message` does for .ogg — mirror that
   pattern including size guards and error handling). Caption text (if any)
   is the message text.
3. Per image: ffmpeg downscale to `vision_max_edge_px` longest side + JPEG
   re-encode (q~4), async subprocess mirroring `_ogg_to_pcm` (:1144). Cap
   output ~400KB (lower quality retry if over). Base64 → `data:image/jpeg;base64,...`
4. If `vision` is disabled: reply ONCE per photo with a short note ("I can't
   see images yet" / mention if disabled) — fix the silent-drop bug.
5. Pass images through `_on_message` — see §3.

## §3 — Platform message type

Extend the incoming-message path so attachments ride along. Find the seam in
`PlatformRunner.on_message` (runners.py) and the orchestrator's turn input:
add an optional `images: list[str] | None` (data URLs) parameter, defaulting
to None, keeping every existing caller/source (Matrix, web, voice→text)
back-compatible. The orchestrator stores images on the turn and hands them to
the inference client. Session history: keep images in the transcript for
within-session coherence (the model can refer back), but cap stored images at
the same per-message cap; log the estimated image-token cost per request.

## §4 — Inference client

In the openai-compat request builder: when images present and gating allows,
`content` becomes an array: `[{"type":"text","text":prompt}, {"type":"image_url","image_url":{"url":data_url}}, ...]`.
llamacpp path: ignore images, log warning. Raise/warn clearly if images
present but gating disallows (so misconfig is visible, not silent).
Respect the client's existing timeout/retry machinery (L232 admission control
unchanged — images ride the same single-slot queue).

## §5 — Runtime config + deploy

- `~/Hestia-runtime/config.coder-bot.py` UNAFFECTED. In
  `~/Hestia-runtime/config.runtime.py`: `_telegram_from_env()` gains
  `vision=True` (hardcode for this runtime — Strata is the backend).
- Merge feature branch to the runtime worktree, run runtime gates, restart
  `hestia-serve.service`, verify it polls clean.
- Acceptance: Dylan sends a photo to the main Hestia bot; model describes it.

## §6 — Tests

- Adapter: photo handler with mock PhotoSize/bot (mirror
  tests/unit/test_telegram_adapter.py voice patterns) — download, ffmpeg
  call shape, disabled-vision reply path, caption passthrough.
- ffmpeg transform: use real ffmpeg (it's installed) in an integration test;
  assert output dimensions ≤ cap and base64 decodes as JPEG.
- Client: openai-compat payload with images (mock httpx), llamacpp strip path.
- Orchestrator: images on turn → present in request; None elsewhere.
- Config gating: vision×server_type matrix.
- No regressions in existing suites.

## Handoff

Per-item accounting vs this spec; gate results; the live photo test outcome;
image-token cost observed; any Strata payload surprises (e.g. if it rejects
standard OpenAI image_url parts — report, don't paper over).

## Critical rules recap

- Strata is FROZEN: no restart, no reconfigure, no flags.
- No new Python dependencies; ffmpeg only.
- No sync I/O in async paths; narrow excepts; every config field wired.
- Line length 120; conventional commits; branch
  `feature/l234-telegram-vision` from `develop` in ~/Hestia; push when green.
- Quality gates: pytest (unit+integration), mypy src/hestia, ruff check.
