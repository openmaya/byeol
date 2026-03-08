#!/bin/bash
set -e

echo "==============================="
echo "  Byeol Installer (RPi3)"
echo "==============================="
echo ""

# --- System packages ---
echo "[1/5] Installing system packages..."

sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 \
    python3-pip \
    python3-venv \
    chromium \
    chromium-driver

# yt-dlp via pip (apt version is often outdated)
if ! command -v yt-dlp &>/dev/null; then
    pip3 install --break-system-packages yt-dlp 2>/dev/null || pip3 install yt-dlp 2>/dev/null || true
fi

# --- Project directory ---
INSTALL_DIR="$HOME/byeol"
echo "[2/5] Setting up project in $INSTALL_DIR..."

if [ -d "$INSTALL_DIR" ]; then
    echo "  Directory exists. Updating files..."
else
    mkdir -p "$INSTALL_DIR"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
    for f in main.py config.py llm.py search.py memory.py agent.py cron.py fileops.py media.py requirements.txt; do
        if [ -f "$SCRIPT_DIR/$f" ]; then
            cp "$SCRIPT_DIR/$f" "$INSTALL_DIR/"
        fi
    done
else
    echo "  Already running from install directory. Skipping file copy."
fi

# --- Python venv ---
echo "[3/5] Creating Python virtual environment..."
cd "$INSTALL_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
pip install yt-dlp -q
deactivate

# --- .env setup ---
echo "[4/5] Configuring environment..."
if [ ! -f "$INSTALL_DIR/.env" ]; then
    echo ""
    read -p "Telegram Bot Token: " TG_TOKEN
    read -p "Google API Key (Gemini): " GOOGLE_KEY
    read -p "Anthropic API Key (optional, Enter to skip): " ANTHROPIC_KEY
    read -p "Your Telegram User ID (comma-separated): " USER_IDS
    read -p "Default LLM [gemini/claude] (default: gemini): " DEFAULT_LLM
    DEFAULT_LLM=${DEFAULT_LLM:-gemini}
    read -p "Media directory for downloads (default: ~/media): " MEDIA_DIR
    MEDIA_DIR=${MEDIA_DIR:-~/media}

    cat > "$INSTALL_DIR/.env" <<EOF
TELEGRAM_BOT_TOKEN=$TG_TOKEN
GOOGLE_API_KEY=$GOOGLE_KEY
ANTHROPIC_API_KEY=$ANTHROPIC_KEY
DEFAULT_LLM=$DEFAULT_LLM
ALLOWED_USER_IDS=$USER_IDS
MEDIA_DIRS=$MEDIA_DIR
MEDIA_THRESHOLD=0.7
EOF
    chmod 600 "$INSTALL_DIR/.env"
    echo "  .env created (permissions: owner-only)."

    # Create media directory
    eval mkdir -p "$MEDIA_DIR"
    mkdir -p "$HOME/files"
else
    echo "  .env already exists. Skipping."
fi

# --- Service setup (systemd) ---
echo "[5/5] Setting up systemd service..."

SERVICE_FILE="/etc/systemd/system/byeol.service"

sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Byeol Personal AI Assistant
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/main.py
Restart=always
RestartSec=10
Environment=DISPLAY=:0

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable byeol.service
sudo systemctl restart byeol.service

echo ""
echo "==============================="
echo "  Installation complete!"
echo "==============================="
echo ""
echo "  Install dir : $INSTALL_DIR"
echo "  Service     : byeol.service (systemd)"
echo ""
echo "  Commands:"
echo "    sudo systemctl status byeol    # Check status"
echo "    sudo systemctl stop byeol      # Stop"
echo "    sudo systemctl restart byeol   # Restart"
echo "    journalctl -u byeol -f         # View logs"
echo ""
echo "  Open Telegram and send /start to your bot!"
