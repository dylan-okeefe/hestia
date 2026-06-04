# Session Summary — 2026-05-30

## Overview

Full system diagnosis and configuration session covering Cursor IDE crash loop, llama.cpp server optimization, systemd service cleanup, GPU driver state recovery, remote access fallbacks, and two failed job search test attempts.

---

## 1. Cursor IDE Crash Investigation

### Symptoms
- Cursor repeatedly crashed with `renderer process gone (reason: crashed, code: 11)` — SIGSEGV
- Extension host crashed with code 139 — SIGSEGV in extension host
- `apport` process consumed 99.4% CPU for 9+ minutes processing crash dumps
- 7+ crashes in a 20-minute window

### Root Cause
**GPU driver state corruption**, not profile corruption.
- Fresh user-data-dir + GPU acceleration = crashed
- Fresh user-data-dir + `--disable-gpu` = stable
- The NVIDIA driver stack was poisoned after llama.cpp build OOMs, hard resets, and cold boots
- A 482 MB corrupted `state.vscdb` was found and removed (bonus cleanup, not the crash trigger)

### Fixes Applied
- Killed runaway `apport` process (PID 20035)
- Cleared all GPU caches: `~/.cache/nvidia/GLCache`, `~/.nv/ComputeCache`, `~/.cache/mesa_shader_cache*`
- Patched `/usr/share/applications/cursor.desktop` to pass `--disable-gpu`
- Added bash alias: `alias cursor="/usr/share/cursor/cursor --disable-gpu"`
- Disabled `apport` service entirely to prevent future crash-report hangs

### Post-Reboot Verification
- After reboot, Cursor GPU acceleration worked again (driver state cleared)
- Kept `--disable-gpu` workaround permanent per user preference

---

## 2. llama.cpp Server Configuration Evolution

### Model
- **Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf** (21 GB)
- **mmproj-F16.gguf** (858 MB) for vision support
- Stored in `/home/dylan/models/qwen36-35b-a3b/`

### Configuration Changes

#### Before Session
| Parameter | Value |
|-----------|-------|
| Context (`-c`) | 65,536 |
| Slots (`-np`) | 1 |
| GPU layers (`-ngl`) | 99 |
| MoE offloading | `-cmoe` |
| Cache type | `turbo3` for K and V |
| mlock | ~~enabled~~ (removed due to lockups) |

#### After Session
| Parameter | Value |
|-----------|-------|
| Context (`-c`) | **131,072** |
| Slots (`-np`) | **2** |
| GPU layers (`-ngl`) | 99 |
| MoE offloading | `-cmoe` |
| Cache type | `turbo3` for K and V |
| Threads | `-t 4 -tb 4` |
| Memory map | `--no-mmap` |
| Fit | `--fit on --fit-ctx 4096` |
| Jinja | `--jinja` |
| Thinking disabled | `--chat-template-kwargs '{"enable_thinking":false}'` |
| Slot save path | `/home/dylan/.hermes/cache/slots/` |
| mlock | **removed** |

### Performance Metrics
- **Prompt processing**: ~37 tok/s
- **Generation speed**: ~13-16 tok/s sustained
- **GPU memory**: ~4.4 GB (model buffers + KV cache)
- **KV cache at 2 slots × 65K**: ~500 MB (turbo3)
- **Host RAM**: ~19-20 GB for expert weights
- **VRAM headroom**: ~7.5 GB free of 12 GB total

### Key Discoveries
- `turbo3` cache quantization is **essential** — keeps KV cache at ~500 MB instead of 6–8 GB
- `--mlock` caused **system lockups** (100% CPU for >1 hour, 19 GB pinned) — permanently removed
- `--slot-save-path` resolved Hestia 501 errors on session restore

---

## 3. Hestia Runtime Configuration

### File: `/home/dylan/Hestia-runtime/config.runtime.py`

| Parameter | Before | After |
|-----------|--------|-------|
| `model_name` | Qwen3.5-9B-DeepSeek-V4-Flash-Q4_K_M.gguf | **Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf** |
| `context_length` | 32,768 | **65,536** (per slot, matches 131072 / 2) |
| `default_reasoning_budget` | 2,048 | unchanged |
| `max_tokens` | 4,096 | unchanged |

Note: `context_length` represents the per-slot context budget used by Hestia's policy engine.

---

## 4. Systemd Service Cleanup

### Removed Legacy Services
| Service | Status | Reason |
|---------|--------|--------|
| `hermes.service` | **purged** | Legacy Hermes agent harness — stuck in 1,887-restart loop, was spamming system |
| `hermes-llama.service` | **disabled + removed** | Legacy Qwen3.5 server |
| `hestia-matrix.service` | **disabled + removed** | Matrix bot (unused) |
| `hestia-telegram.service` | **disabled + removed** | Telegram bot (unused) |
| `hermes-gateway.service` | **disabled + removed** | Agent harness gateway (unused) |

### Active Services
| Service | Status | Purpose |
|---------|--------|---------|
| `hestia-llama.service` | enabled | Qwen3.6 35B MoE inference server |
| `hestia-serve.service` | enabled | Hestia API/web dashboard |

### Service Hardening (`hestia-llama.service`)
Added to prevent future lockups:
- `MemoryMax=42G` (raised from initial 32G which was too tight)
- `MemorySwapMax=8G`
- `OOMScoreAdjust=1000` (first to be killed by OOM killer)
- `CPUWeight=50`
- `IOWeight=50`
- `Restart=always`
- `TimeoutStartSec=180`

---

## 5. System Protections Added

### ZRAM Swap
- Configured 16 GB zram device (`/dev/zram0`)
- Algorithm: `lzo-rle`
- Priority: 100 (higher than disk swap)
- Helps with memory pressure without disk thrashing

### OOM Killer Tuning
- `vm.oom_kill_allocating_task=1` — kill the process that triggered OOM, not a random one
- `vm.overcommit_ratio=95` — slightly more conservative memory overcommit
- Both settings persisted in `/etc/sysctl.conf`

### Apport Disabled
- `enabled=0` in `/etc/default/apport`
- Service stopped and disabled
- Prevents crash-report processing from consuming 99% CPU for extended periods

### Build Safety Wrapper
Created `/home/dylan/llama.cpp-turboquant/safe_build.sh`:
- Limits parallelism to `-j1` by default (prevents nvcc OOM)
- Runs with `nice -n 10` (lower priority, keeps system responsive)
- Configures CUDA + flash-attn build flags

---

## 6. GPU Health & Driver State

### Post-Reboot Status (Healthy)
| Metric | Value |
|--------|-------|
| Driver | 580.142 |
| CUDA | 13.0 |
| GPU | RTX 3060 12 GB |
| Temperature | 37–43°C |
| Power | 14W idle, 42W loading |
| GPU layers | 41/41 offloaded |
| Errors | None |
| Throttling | None |

### Crash Analysis (Boot -1: 11:37 → 16:59)
- System ran for ~5.5 hours after morning Cursor crashes
- RDP session likely froze around 14:00 when llama-server was restarted with 2-slot config
- **Root cause of RDP freeze**: NVIDIA display driver (DRM/KMS path) froze under GPU memory reallocation stress
- Compute path remained functional (gpu-watchdog, llama-server loading succeeded)
- **Final crash after 16:59**: `hermes.service` restart loop (1,887 attempts) caused resource exhaustion

### Key Insight
NVIDIA driver corruption manifests as: **compute works, display dies**. Xorg freezes but `nvidia-smi` and CUDA processes keep running. A reboot clears the driver state.

---

## 7. Remote Access Fallbacks

### Problem
Router blocks all traffic except SSH (22) and RDP (3389) between subnets.

### Solution: SSH Tunnel for Cockpit
Added to `~/.ssh/config` on user's Mac:
```
Host hestia-cockpit
    HostName 192.168.2.108
    User dylan
    LocalForward 9090 localhost:9090
```

Usage:
```bash
ssh hestia-cockpit
# open https://localhost:9090 in browser
```

### Services Available
| Service | Port | Access Method |
|---------|------|---------------|
| SSH | 22 | Direct (any subnet with routing) |
| Cockpit | 9090 | SSH tunnel or same subnet |
| xrdp | 3389 | Direct (router-allowed) |

---

## 8. Job Search Test Attempts

### Prompt
`/home/dylan/Documents/Job Search/model-evaluation-prompt-v8.md`
- Asks agent to find 5 real job postings for Senior Frontend Engineer
- Instructs use of `browser_get` and `append_to_file` tools directly
- Targets Built In Boston and similar job boards

### Attempt 1 (Earlier Today, Before Session Context)
- Exit code: 0
- Assistant error: "Something went wrong. The operator has been notified."
- Output: header only (4 lines)
- Server processed 23,284 prompt tokens

### Attempt 2 (This Session)
- Ran from 22:50 to 22:53:55 (~4 minutes)
- Server processed 34,432 prompt tokens
- Generated 64 tokens at 13.6 tok/s
- Assistant error: "I'm having trouble responding right now. Please try again."
- Output: header only (5 lines)
- Root cause: Model could not produce valid tool calls in Hestia's expected format

### Current Output File
`/home/dylan/Documents/Job Search/remote_software_development_jobs.md` — contains header only, backed up before each attempt.

---

## 9. APEX Model Status

- **Downloaded**: `Qwen3.6-35B-A3B-APEX-I-Quality.gguf` (22 GB) to `/home/dylan/models/qwen36-35b-a3b-apex/`
- **Status**: Incompatible with current llama.cpp (`63b832b`)
- **Requires**: llama.cpp `b8797+`
- **Build attempt**: `b9418` failed twice — `nvcc` OOM on flash-attention template instances even with `-j1`
- **Deferred**: Until Ryzen 7 3700X + B550M upgrade (more RAM and CPU cores)

---

## 10. Switch Script & Registry

### `/home/dylan/models/switch_model.sh`
- Updated `qwen36-35b-a3b` case with current flags
- Removed `--mlock`
- Added `--fit on --fit-ctx 4096`, `--jinja`, `--chat-template-kwargs`

### `/home/dylan/models/registry.yaml`
- Updated to point to Qwen3.6 35B-A3B UD-Q4_K_XL
- Context: 65536 → 131072

---

## 11. Open Questions / Next Steps

1. **Job search test**: Needs a different approach — model struggles with Hestia's tool-calling format for browser automation. Consider simpler prompt or different model.
2. **APEX model**: Blocked on llama.cpp upgrade. Requires new hardware or a build environment with more RAM.
3. **Monitor stability**: 2-slot config is new. Watch for memory pressure or driver issues over the next few days.
4. **Cursor GPU acceleration**: Could be reverted now that driver state is clean, but `--disable-gpu` is harmless and provides safety margin.

---

## Files Modified

- `/home/dylan/.config/systemd/user/hestia-llama.service`
- `/home/dylan/Hestia-runtime/config.runtime.py`
- `/usr/share/applications/cursor.desktop`
- `/etc/default/apport`
- `/etc/sysctl.conf`
- `~/.bashrc` (Cursor alias)
- `/home/dylan/llama.cpp-turboquant/safe_build.sh` (created)
- `~/.ssh/config` (on Mac, via instructions)

## Files Removed

- `/etc/systemd/system/hermes.service`
- `~/.config/systemd/user/hermes-llama.service`
- `~/.config/systemd/user/hestia-matrix.service`
- `~/.config/systemd/user/hestia-telegram.service`
- `~/.config/systemd/user/hermes-gateway.service`
- `~/.config/Cursor/User/globalStorage/state.vscdb` (482 MB corrupted)
- Various GPU/shader caches
