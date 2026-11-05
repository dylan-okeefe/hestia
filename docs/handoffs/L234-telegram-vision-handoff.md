# L234 Handoff — Telegram vision pipeline

Card: TaskView #71. Branch: `feature/l234-telegram-vision` (from develop +
L232 merge — develop does not yet contain L232, so this branch carries it;
merging to develop later brings L232 along). Spec:
`docs/development-process/loops/L234-telegram-vision.md`.

## What landed

- **Config** (`TelegramConfig`): `vision` (default off), `vision_max_images_per_message=4`,
  `vision_max_edge_px=1024`; env-wired (`HESTIA_TELEGRAM_VISION*`).
- **Adapter**: `filters.PHOTO` handler; largest PhotoSize download (mirrors
  voice pattern, 10MB guard); ffmpeg downscale+JPEG (async, ~400KB cap with
  quality/scale retries); caption → text; disabled-vision now replies instead
  of silently dropping.
- **Message path**: `IncomingMessageCallback` gains a 6th `images` param
  (protocol quirk: no defaults on `__call__`, names must match — see
  platforms/base.py); orchestrator stores images on the user `Message` +
  `TurnContext`; **persisted** in `messages.images` (runtime migration m012)
  so later turns in a session keep sight; compaction archives drop images
  (lossy by design).
- **Client**: `message_to_dict` emits standard OpenAI content arrays
  (`text` + `image_url` data-URL parts) only when images present; gating =
  `vision AND server_type=="openai-compat"`, every other combination strips
  with a WARNING (llamacpp/Ornith never receives images); `count_request`
  also strips (keeps base64 away from /tokenize); image-token estimate
  (`(edge/28)²` from the JPEG SOF marker, `core/vision.py`) feeds context
  accounting so history photos don't blow the budget.
- **Runtime**: `config.runtime.py` `_telegram_from_env()` sets `vision=True`;
  merged + hestia-serve restarted 2026-10-21 16:36 EDT, clean startup,
  migration applied.

## Gates

Dev: 2446 passed / 6 skipped / 1 pre-existing fail (numpy-missing voice
test, fails on develop); mypy 1 pre-existing numpy error; ruff clean.
Runtime: 2485→2486 passed after fixing the L233×L234 callback-contract union
(test stubs updated to the 6-arg signature); mypy clean (232 files); ruff clean.

## Cross-branch note (for the develop merge)

`feature/l233-telegram-coding-agent-bridge` and this branch both touch
`telegram_adapter.py`'s `_on_message` call and the test stubs. Runtime union
is fixed (commit on the runtime line). When both land on develop, expect the
same 6-arg contract conflict in `test_agent_bridge.py` — resolution is the
same: stubs take the 6-arg signature.

## Risks flagged (unverifiable until live test)

- Strata's acceptance of OpenAI-native `image_url` base64 data-URL parts is
  ASSUMED (llama.cpp server historically preferred `image_data` + content
  refs; recent builds accept image_url). The live photo test decides; if
  rejected, the fix is client-side payload shape only.
- If Strata's streaming path mishandles multimodal chunks, set
  `inference.stream` off in config.runtime.py as a workaround.
- 1024px ≈ ~1.3K est. tokens/photo; 4-photo cap ≈ 5.2K tokens.

## Pending

- Dylan sends a photo to the main Hestia bot — acceptance test.
- Plan B only if quality fails: small VLM on the Proxmox box (card #71 note).
