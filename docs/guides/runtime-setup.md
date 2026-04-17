# Runtime setup guide

How to configure Hestia's inference and slot settings for reliable operation.

---

## Picking a `base_url` and matching `slot_dir`

`InferenceConfig.base_url` must point at the llama-server Hestia will use.
`SlotConfig.slot_dir` must match that server's `--slot-save-path`.

### Mode A — Dedicated llama-server (recommended)

Copy `deploy/hestia-llama.service` to your systemd user directory and start it:

```bash
sudo cp deploy/hestia-llama.service /etc/systemd/user/hestia-llama@$USER.service
sudo systemctl daemon-reload
sudo systemctl start hestia-llama@$USER
```

Then in `config.py`:

```python
from pathlib import Path
from hestia.config import HestiaConfig, InferenceConfig, SlotConfig

config = HestiaConfig(
    inference=InferenceConfig(
        base_url="http://127.0.0.1:8001",
        model_name="Qwen3.5-9B-UD-Q4_K_XL.gguf",
    ),
    slots=SlotConfig(
        slot_dir=Path("/opt/hestia/slots"),
        pool_size=4,
    ),
)
```

### Mode B — Shared with another local LLM service

If you already run a llama-server for another project (e.g. Hermes), you can
point Hestia at it:

```python
config = HestiaConfig(
    inference=InferenceConfig(
        base_url="http://127.0.0.1:8001",  # wherever the shared server lives
        model_name="Qwen3.5-9B-UD-Q4_K_XL.gguf",
    ),
    slots=SlotConfig(
        slot_dir=Path.home() / ".hermes" / "cache" / "slots",  # must match --slot-save-path
        pool_size=4,
    ),
)
```

**Warning:** If `slot_dir` does not match `--slot-save-path`, llama.cpp returns
HTTP 400 "Invalid filename" on every slot save/restore. The session will still
work, but KV-cache snapshots never reach disk, so resuming a warm session
requires re-processing the full history.

### Mode A alt-port — Dedicated on 8002

If port 8001 is occupied by another service, use the drop-in example:

```bash
sudo cp deploy/hestia-llama.alt-port.service.example \
     /etc/systemd/user/hestia-llama@$USER.service
```

Then set `base_url="http://127.0.0.1:8002"` and `slot_dir=Path("/opt/hestia/slots")`.

---

## Verifying isolation

Check which server is on which port:

```bash
curl -s http://127.0.0.1:8001/health
curl -s http://127.0.0.1:8001/v1/models

curl -s http://127.0.0.1:8002/health
curl -s http://127.0.0.1:8002/v1/models
```

Only one should respond on each port. If both respond with the same model,
they are the same process (or two processes bound to the same port, which
systemd should prevent).

---

## Per-slot context calculation

llama-server divides `--ctx-size` by `--parallel` to get the per-slot budget.

| `--ctx-size` | `--parallel` | Per-slot context | Notes |
|-------------|--------------|------------------|-------|
| 8192 | 2 | 4096 | Minimum viable |
| 16384 | 4 | 4096 | Fits 7-9B Q4 on 12 GB |
| 32768 | 4 | 8192 | Comfortable for long sessions |
| 32768 | 6 | 5461 | Good for multi-session on 24 GB |

Set `InferenceConfig.context_length` to the **per-slot** value, not the total.
Hestia's `ContextBuilder` uses this to decide how much history to keep.

---

## Troubleshooting

### "Invalid filename" on slot save

`slot_dir` does not match `--slot-save-path`. Fix the path in `config.py` and
restart Hestia. The slot file itself is written by llama-server, not by Hestia.

### Phantom slot-restore failures

If a session is WARM but restore fails with HTTP 400, the saved snapshot may
have been deleted or the `slot_dir` may have changed. The session falls back to
COLD (rebuild from messages), which is slower but correct.

### Context budget warnings

If you see "This session has grown past my context budget", the protected block
(system prompt + identity + memory epoch + skill index + new user message)
exceeds the per-slot budget. Options:

1. Reduce `IdentityConfig.max_tokens`.
2. Shorten `SOUL.md`.
3. Increase `--ctx-size / --parallel` (requires more VRAM).
4. Run `/reset` to archive the session and start fresh.
