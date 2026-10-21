# L232 — Inference Backend Profiles — Handoff

## What landed

Branch `feature/l232-inference-backend-profiles` (from `dummy/hestia-main`):

- `d93b1e18` feat(inference): backend profiles — openai-compat gating, admission control, slot no-op
- `b2b6ef80` test(inference): L232 backend profile coverage
- `9e5f32ef` fix(deploy): decouple hestia-serve from hestia-llama auto-start
- `46bdcf51` chore: refresh metrics.json

## Behavior change

`InferenceConfig` gains `server_type` (`"llamacpp"` default | `"openai-compat"`),
`max_inflight_requests` (0 = unlimited), `queue_timeout` (default 120s). All
env-overridable via `HESTIA_INFERENCE_*` with no behavior change for existing
llamacpp configs.

openai-compat profile (Strata, port 8080):
- Request bodies omit `slot_id` and `reasoning_budget`.
- `tokenize()` unavailable; ContextBuilder estimates `len//4` for budgeting
  (all call sites incl. `commands/preview_prompt.py` route through one helper).
- `health()` probes `GET {base}/v1/models`.
- SlotManager becomes a no-op (`acquire()` → `None`); no `/slots` HTTP, no disk.
- Client-side admission: semaphore over `max_inflight_requests`; queue wait
  beyond `queue_timeout` raises `InferenceBusyError`, which the orchestrator
  surfaces verbatim as "I'm busy working on another request right now — please
  try again in a moment."

deploy/hestia-serve.service: dropped `Wants=/After=hestia-llama.service`.
Rationale: inference backend is per-profile and model services are mutually
exclusive on RAM; the Wants pulled Ornith (29GB RAM + 11GB VRAM) up next to
Strata (54GB RAM + 23GB VRAM) on every start/reboot -> guaranteed OOM.

## Runtime deployment (~/Hestia-runtime, branch fix/65-tts-device-cpu)

- Merge commits: `d4712178` (feature) + follow-up merge of 9e5f32ef/46bdcf51.
- `config.runtime.py`: Strata backend (127.0.0.1:8080, qwen3.8-flash-next-iq3_s,
  server_type=openai-compat, max_inflight_requests=2, queue_timeout=120s).
  Backup at /tmp/config.runtime.py.pre-l232.bak.
- Live unit `~/.config/systemd/user/hestia-serve.service` synced (was a stale
  May 11 copy, not a symlink) — Wants now empty, verified via systemctl show.
- hestia-serve active against Strata; hestia-llama inactive. Smoke: `hestia
  health` OK, CLI ask round-trip OK, no platform messages sent.

## Quality gates

- pytest unit+integration: runtime worktree 2412 passed / 0 failed; dev
  worktree has 35 pre-existing failures on clean baseline (doctor/memory-epoch
  family) — zero new.
- mypy: clean (227 files). ruff: 48 = baseline, none new.

## Follow-ups (not in scope)

- health() goes through admission when a semaphore is configured — a probe can
  wait behind inflight requests up to queue_timeout. Cosmetic; revisit if it
  annoys.
- Multi-profile runtime switching (UI/CLI to pick backend without editing
  config) — future loop if Dylan wants it.
- Strata `--parallel 2` retest after upstream fixes its silent 256k crash
  (cards #67/#68 notes) — would change the max_inflight recommendation.
- Flash-Next (8002) works unchanged under the llamacpp profile, but its model
  files are parked on the SATA SSD (/mnt/storage) — restore to ~/models before
  using hestia-flashnext.service (card #67 note).
