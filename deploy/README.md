# Hestia deployment

Systemd service templates for running Hestia as a persistent service on Linux.

---

## Prerequisites

- **llama.cpp server** (`llama-server`) installed and accessible
- **uv** for Python environment management
- **NVIDIA GPU** with appropriate drivers (or CPU-only with adjusted settings)
- A model file (e.g., `Qwen3.5-9B-UD-Q4_K_XL.gguf`)

## Files

| File | Purpose |
|------|---------|
| `hestia-llama.service` | llama.cpp inference server with KV-cache slots |
| `hestia-agent.service` | Hestia agent (Telegram bot + scheduler daemon) |
| `install.sh` | Copies services to systemd and reloads |
| `example_config.py` | Configuration template — copy and customize |

## Architecture

Two systemd units work together:

```
hestia-llama@user  →  llama-server on :8001 (inference)
       ↑
hestia-agent@user  →  hestia telegram (bot + scheduler)
```

`hestia-agent` depends on `hestia-llama` — systemd starts them in the right
order and restarts on failure.

The agent service runs `hestia telegram`, which starts both the Telegram bot
and the scheduler daemon in a single process. The scheduler fires tasks through
the same orchestrator, sharing the KV-cache slot pool.

---

## Setup

### 1. Create the deployment directory

```bash
sudo mkdir -p /opt/hestia/{models,data/artifacts,slots}
sudo chown -R $USER:$USER /opt/hestia
```

### 2. Install Hestia

```bash
cd /opt/hestia
git clone https://github.com/dylanokeefe/hestia.git .
uv sync
```

### 3. Download a model

```bash
# Example: Qwen 3.5 9B (fits in 12 GB VRAM with 4-slot, 16K context)
huggingface-cli download unsloth/Qwen3.5-9B-UD-Q4_K_XL-GGUF \
    --local-dir /opt/hestia/models/
```

### 4. Configure

```bash
cp deploy/example_config.py /opt/hestia/config.py
```

Edit `config.py`:

```python
from pathlib import Path
from hestia.config import (
    HestiaConfig, InferenceConfig, SlotConfig,
    SchedulerConfig, StorageConfig, TelegramConfig,
)

config = HestiaConfig(
    inference=InferenceConfig(
        base_url="http://127.0.0.1:8001",
        model_name="Qwen3.5-9B-UD-Q4_K_XL.gguf",
        default_reasoning_budget=2048,
        max_tokens=1024,
    ),
    slots=SlotConfig(
        slot_dir=Path("/opt/hestia/slots"),
        pool_size=4,                            # must match llama-server --slots
    ),
    scheduler=SchedulerConfig(
        tick_interval_seconds=5.0,
    ),
    storage=StorageConfig(
        database_url="sqlite+aiosqlite:////opt/hestia/data/hestia.db",
        artifacts_dir=Path("/opt/hestia/data/artifacts"),
        allowed_roots=["/opt/hestia", "/home/YOUR_USER/documents"],
    ),
    telegram=TelegramConfig(
        bot_token="YOUR_BOT_TOKEN",
        allowed_users=["YOUR_TELEGRAM_USER_ID"],
    ),
    system_prompt="You are Hestia, a helpful personal assistant.",
    max_iterations=10,
)
```

### 5. Initialize the database

```bash
cd /opt/hestia
uv run hestia --config config.py init
```

### 6. Edit the service files (if needed)

The service files assume:

- llama-server is at `/usr/local/bin/llama-server`
- Model is at `/opt/hestia/models/Qwen3.5-9B-UD-Q4_K_XL.gguf`
- Hestia venv is at `/opt/hestia/.venv/`

If your paths differ, edit `hestia-llama.service` and `hestia-agent.service`
before installing.

### 7. Install and start

```bash
cd /opt/hestia/deploy
sudo ./install.sh $USER

sudo systemctl start hestia-llama@$USER
sudo systemctl start hestia-agent@$USER

# Enable on boot
sudo systemctl enable hestia-llama@$USER
sudo systemctl enable hestia-agent@$USER
```

### 8. Verify

```bash
# Check both services
systemctl status hestia-llama@$USER hestia-agent@$USER

# Check inference health
curl -s http://localhost:8001/health

# Check logs
journalctl -u hestia-llama@$USER -f
journalctl -u hestia-agent@$USER -f
```

---

## llama-server flags reference

The `hestia-llama.service` template uses these flags:

| Flag | Value | Purpose |
|------|-------|---------|
| `--model` | Path to .gguf | Model file |
| `--host` | `127.0.0.1` | Listen on localhost only |
| `--port` | `8001` | Must match `InferenceConfig.base_url` |
| `--n-gpu-layers` | `99` | Offload all layers to GPU |
| `--ctx-size` | `16384` | Total context length across all slots |
| `--slots` | `4` | Must match `SlotConfig.pool_size` |
| `--flash-attn` | `on` | Flash attention (always recommended) |
| `--cache-type-k` | `turbo3` | KV-cache key quantization (~4x VRAM savings) |
| `--cache-type-v` | `turbo3` | KV-cache value quantization |
| `--jinja` | — | Chat template support (required for Qwen) |
| `--reasoning-format` | `deepseek` | Reasoning token extraction |
| `--slot-save-path` | `/opt/hestia/slots` | Disk checkpoint directory |

### Tuning for different hardware

**8 GB VRAM:**
```
--ctx-size 8192 --slots 2 --cache-type-k q4_0 --cache-type-v q4_0
```

**12 GB VRAM (default):**
```
--ctx-size 16384 --slots 4 --cache-type-k turbo3 --cache-type-v turbo3
```

**24 GB VRAM:**
```
--ctx-size 32768 --slots 6 --cache-type-k q8_0 --cache-type-v q8_0
```

---

## Service behavior

- Both services run as the specified user (template `@` syntax)
- `hestia-llama` restarts after 5 seconds on failure
- `hestia-agent` restarts after 10 seconds on failure
- `hestia-agent` won't start until `hestia-llama` is running
- Agent logs go to journald with `PYTHONUNBUFFERED=1` for real-time output

---

## Updating

```bash
cd /opt/hestia
git pull
uv sync
sudo systemctl restart hestia-agent@$USER
# Restart hestia-llama only if the model or server config changed
```

If schema changed between versions:
```bash
uv run alembic upgrade head
```
