<div align="center">

# Byeol (별) ⭐

### Your personal AI assistant that lives on a Raspberry Pi.

**Private. Always-on. Yours.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-c51a4a.svg)](https://www.raspberrypi.com/)
[![Telegram Bot](https://img.shields.io/badge/interface-Telegram-26A5E4.svg)](https://telegram.org/)

[Features](#features) · [Quick Start](#quick-start) · [Architecture](#architecture) · [Configuration](#configuration) · [Commands](#commands) · [Contributing](#contributing)

</div>

---

## What is Byeol?

Byeol is a personal AI assistant that runs on a Raspberry Pi 3 and talks to you through Telegram. It remembers everything about you, tracks your goals, keeps a journal, searches the web, downloads media, and schedules recurring tasks.

Your personal data (profile, goals, journal, memories, files) stays on your Pi. Conversation prompts are sent to LLM APIs (Gemini/Claude/Ollama) for inference — or run fully local with Ollama.

### Why Byeol?

| | Cloud AI Services | Byeol |
|---|---|---|
| **Privacy** | All your data on their servers | Personal data on your device; use Ollama for fully local inference |
| **Availability** | Service shuts down, you lose everything | You own your data forever |
| **Always-on** | Requires browser/app open | Runs 24/7 on your Pi |

## Features

**AI Assistant & Life Coach**
- Autonomous [ReAct agent loop](https://arxiv.org/abs/2210.03629) with tool calling
- Auto-learns your profile from natural conversation
- Goal tracking with progress updates
- Daily journaling with mood tracking
- Proactive coaching — not just answering questions

**Web & Media**
- Web search via DuckDuckGo (headless Chromium)
- Page reading and summarization
- YouTube & Instagram video downloading
- Auto storage management (cleanup at 70% capacity)

**Productivity**
- Built-in cron scheduler for recurring tasks
- File management (read, write, move, organize)
- Key-value memory store
- Conversation history (30 turns per chat)

**Infrastructure**
- Runs on Raspberry Pi 3 (1GB RAM, ARM)
- Telegram bot interface — use the app you already have
- Multi-LLM: Google Gemini + Anthropic Claude + Ollama (local/remote)
- systemd service with auto-restart
- One-script installation

## Quick Start

### Prerequisites

- Raspberry Pi 3/4/5 running Debian (Bookworm/Trixie)
- [Telegram Bot Token](https://core.telegram.org/bots#how-do-i-create-a-bot) (free, from @BotFather)
- [Google API Key](https://aistudio.google.com/apikey) (free tier for Gemini)
- Anthropic API Key (optional, for Claude backend)
- Ollama server (optional, for local/remote open-source models)

### Install

SSH into your Pi and run:

```bash
git clone https://github.com/openmaya/byeol.git
cd byeol
chmod +x install.sh
./install.sh
```

The installer will:
1. Install system packages (Python, Chromium, chromedriver)
2. Create a Python virtual environment
3. Prompt you for API keys and Telegram user ID
4. Set up a systemd service that starts on boot

That's it. Open Telegram and send `/start` to your bot.

### Manual Setup

If you prefer manual installation:

```bash
sudo apt install python3 python3-venv chromium chromium-driver
git clone https://github.com/openmaya/byeol.git
cd byeol
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install yt-dlp
cp .env.example .env   # Edit with your keys
python main.py
```

## Architecture

```
Telegram ──► main.py (Bot + JobQueue)
                │
                ├──► agent.py (ReAct Loop)
                │       │
                │       ├──► llm.py (Gemini / Claude / Ollama)
                │       ├──► search.py (DuckDuckGo + Page Reader)
                │       ├──► memory.py (Profile, Goals, Journal)
                │       ├──► fileops.py (Sandboxed File I/O)
                │       ├──► media.py (YouTube/Instagram + Storage)
                │       └──► cron.py (Scheduled Tasks)
                │
                └──► JobQueue (Cron Execution)
```

### Agent Loop

Byeol uses a ReAct (Reason + Act) pattern. On each message:

1. The agent receives user input + full context (profile, goals, journal, memories)
2. The LLM decides which tool to call (search, remember, add_goal, etc.)
3. The tool executes and returns results
4. The LLM reasons about the results and either calls another tool or responds
5. Loop continues until the agent calls `done` with a final answer (max 5 steps)

### Tool System

The agent has access to 18 tools:

| Category | Tools |
|----------|-------|
| **Web** | `search`, `read` |
| **Memory** | `remember`, `recall`, `profile` |
| **Goals** | `add_goal`, `goal_progress`, `complete_goal` |
| **Journal** | `journal` |
| **Scheduling** | `cron_add`, `cron_remove`, `cron_list` |
| **Files** | `file_list`, `file_read`, `file_write`, `file_move`, `file_mkdir` |
| **Media** | `yt_download`, `storage_status`, `media_list` |

## Configuration

All configuration is in `.env`:

```bash
# Required
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
GOOGLE_API_KEY=your-google-gemini-api-key
ALLOWED_USER_IDS=123456789    # Comma-separated Telegram user IDs

# Optional
ANTHROPIC_API_KEY=your-anthropic-api-key
DEFAULT_LLM=gemini            # gemini, claude, or ollama
OLLAMA_BASE_URL=http://your-server:11434  # Ollama server URL
FILE_ROOT=~/files             # Sandboxed file directory
MEDIA_DIRS=~/media            # Media download directory (comma-separated)
MEDIA_THRESHOLD=0.7           # Auto-cleanup threshold (0.0-1.0)
TZ=Asia/Seoul                 # Timezone for cron scheduling (default: UTC)
```

### LLM Backends

| Backend | Model | Use Case |
|---------|-------|----------|
| Gemini | gemini-2.5-flash | Default. Fast, free tier available |
| Claude | claude-haiku-4-5 | Optional. Switch with `/llm claude` |
| Ollama | Any model on server | Local/remote open-source models. Switch with `/llm ollama` |

Use `/llm` (no arguments) to see an interactive picker. When selecting Ollama, available models are fetched from the server and shown as buttons.

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Show welcome message |
| `/search <query>` | Search the web |
| `/read <url>` | Read and summarize a webpage |
| `/goals` | Show active goals |
| `/journal` | Show recent journal entries |
| `/profile` | Show what Byeol knows about you |
| `/cron add <name> <cron> <action>` | Schedule a recurring task (processed by AI agent) |
| `/cron add <name> <cron> say:<message>` | Schedule a direct message (sent as-is, no AI) |
| `/cron rm <name>` | Remove a scheduled task |
| `/cron list` | List all scheduled tasks |
| `/mem list` | Show stored memories |
| `/mem set <key> <value>` | Store a memory |
| `/mem del <key>` | Delete a memory |
| `/llm` | Interactive LLM picker (Gemini/Claude/Ollama) |
| `/llm <gemini\|claude\|ollama>` | Switch LLM backend |
| `/clear` | Clear conversation history |

Most features work through natural conversation — just talk to Byeol and it will figure out what to do.

## Service Management

```bash
# Check status
sudo systemctl status byeol

# View logs
journalctl -u byeol -f

# Restart
sudo systemctl restart byeol

# Stop
sudo systemctl stop byeol
```

## Security

- **API keys** stored in `.env` with `chmod 600` (owner-only)
- **File operations** sandboxed to `FILE_ROOT` — no path traversal
- **URL validation** — media downloads restricted to YouTube/Instagram domains
- **User allowlist** — only authorized Telegram user IDs can interact
- **No shell injection** — all subprocess calls use list args, never `shell=True`
- **Prompt injection defense** — agent ignores instructions found in web pages or files
- **No file deletion** via agent tools — write, move, and read only
- **System disk protection** — auto-cleanup only runs on external mount points

## Project Structure

```
byeol/
├── main.py           # Telegram bot, command handlers, cron execution
├── agent.py          # ReAct agent loop with tool calling
├── llm.py            # Multi-LLM backend (Gemini + Claude + Ollama)
├── search.py         # Web search (DuckDuckGo) + page fetcher
├── memory.py         # Persistent memory (profile, goals, journal)
├── cron.py           # Scheduled task persistence
├── fileops.py        # Sandboxed file operations
├── media.py          # Media download + storage management
├── config.py         # Environment config + path detection
├── install.sh        # One-script installer
├── update.sh         # Quick update (deps + restart, no system packages)
├── requirements.txt  # Python dependencies
└── .env.example      # Configuration template
```

## Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Built for Raspberry Pi. Built for you.**

⭐ Star this repo if Byeol helps you!

</div>
