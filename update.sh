#!/bin/bash
set -e

INSTALL_DIR="$HOME/byeol"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Updating Byeol..."

# Copy source files
if [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
    for f in main.py config.py llm.py search.py memory.py agent.py cron.py fileops.py media.py requirements.txt; do
        if [ -f "$SCRIPT_DIR/$f" ]; then
            cp "$SCRIPT_DIR/$f" "$INSTALL_DIR/"
        fi
    done
fi

# Install/update Python dependencies
cd "$INSTALL_DIR"
source venv/bin/activate
pip install -r requirements.txt -q
deactivate

# Restart service
sudo systemctl restart byeol.service

echo "Done. Check: sudo systemctl status byeol"
