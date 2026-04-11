# Hestia Deployment

Systemd service templates for production deployment.

## Files

- `hestia-llama.service` — llama.cpp inference server (with KV-cache slots)
- `hestia-agent.service` — Hestia agent (Telegram bot + scheduler daemon)
- `install.sh` — Install services to `/etc/systemd/system/`
- `example_config.py` — Configuration template

## Architecture

The agent service runs both the Telegram bot and the scheduler daemon in a single unit. Use `hestia telegram` as the entry point, which spawns the scheduler background thread.

## Installation

```bash
# Copy and customize config
cp example_config.py /opt/hestia/config.py
# Edit config.py with your paths, model, Telegram token, etc.

# Install services
sudo ./install.sh <username>

# Start services
sudo systemctl start hestia-llama@<username>
sudo systemctl start hestia-agent@<username>

# Enable on boot
sudo systemctl enable hestia-llama@<username>
sudo systemctl enable hestia-agent@<username>
```

## Service Dependencies

- `hestia-agent` requires `hestia-llama` (the inference server must be running)
- Both services restart on failure with a 10-second backoff
