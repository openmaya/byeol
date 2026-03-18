import os
import shutil
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DEFAULT_LLM = os.getenv("DEFAULT_LLM", "gemini")
ALLOWED_USER_IDS = [
    int(uid.strip())
    for uid in os.getenv("ALLOWED_USER_IDS", "").split(",")
    if uid.strip()
]
FILE_ROOT = os.path.expanduser(os.getenv("FILE_ROOT", "~/files"))
MEDIA_DIRS = [
    os.path.expanduser(d.strip())
    for d in os.getenv("MEDIA_DIRS", "~/media").split(",")
    if d.strip()
]
MEDIA_THRESHOLD = float(os.getenv("MEDIA_THRESHOLD", "0.7"))

# --- Ollama (remote) ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# --- Auto-detect browser/driver paths (RPi3 / Debian) ---

def _detect_chromium() -> str:
    env_val = os.getenv("CHROMIUM_PATH", "")
    if env_val:
        return env_val
    for c in ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"]:
        if os.path.isfile(c):
            return c
    return shutil.which("chromium") or ""

def _detect_chromedriver() -> str:
    env_val = os.getenv("CHROMEDRIVER_PATH", "")
    if env_val:
        return env_val
    for c in ["/usr/bin/chromedriver", "/usr/local/bin/chromedriver"]:
        if os.path.isfile(c):
            return c
    return shutil.which("chromedriver") or ""

CHROMIUM_PATH = _detect_chromium()
CHROMEDRIVER_PATH = _detect_chromedriver()
