#!/usr/bin/env bash
# Install Hestia systemd services.
# Usage: sudo ./install.sh <username>

set -euo pipefail

USER="${1:?Usage: install.sh <username>}"

cp hestia-llama.service /etc/systemd/system/hestia-llama@.service
cp hestia-agent.service /etc/systemd/system/hestia-agent@.service

systemctl daemon-reload

echo "Services installed. Start with:"
echo "  sudo systemctl start hestia-llama@${USER}"
echo "  sudo systemctl start hestia-agent@${USER}"
echo ""
echo "Enable on boot:"
echo "  sudo systemctl enable hestia-llama@${USER}"
echo "  sudo systemctl enable hestia-agent@${USER}"
