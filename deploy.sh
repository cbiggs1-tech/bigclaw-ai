#!/bin/bash
# Deploy BigClaw to Raspberry Pi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Syncing source files to Pi..."
scp src/*.py bigclaw:~/bigclaw-ai/src/
scp src/tools/*.py bigclaw:~/bigclaw-ai/src/tools/

echo "Syncing config files..."
scp requirements.txt .env bigclaw:~/bigclaw-ai/

echo "Restarting BigClaw service..."
ssh bigclaw "sudo systemctl restart bigclaw"

sleep 2
echo "Checking status..."
ssh bigclaw "sudo systemctl status bigclaw --no-pager"
