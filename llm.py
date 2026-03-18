import aiohttp
import google.generativeai as genai
import anthropic
from config import GOOGLE_API_KEY, ANTHROPIC_API_KEY, OLLAMA_BASE_URL

# --- Gemini ---
genai.configure(api_key=GOOGLE_API_KEY)
_gemini = genai.GenerativeModel("gemini-2.5-flash")

# --- Claude ---
_claude = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

DEFAULT_BACKEND = "gemini"

# Track per-user Ollama model override (chat_id -> model_name)
_ollama_model_override: dict[int, str] = {}


async def list_ollama_models() -> list[str]:
    """Fetch available model names from the Ollama server."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{OLLAMA_BASE_URL}/api/tags",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def set_ollama_model(chat_id: int, model: str):
    _ollama_model_override[chat_id] = model


def get_ollama_model(chat_id: int) -> str:
    return _ollama_model_override.get(chat_id, "")


async def ask(prompt: str, context: str = "", backend: str = "", history: list[dict] = None, chat_id: int = 0) -> str:
    backend = backend or DEFAULT_BACKEND

    if backend == "claude" and _claude:
        return await _ask_claude(prompt, context, history)
    if backend == "ollama":
        return await _ask_ollama(prompt, context, history, chat_id=chat_id)
    return await _ask_gemini(prompt, context, history)


async def _ask_gemini(prompt: str, context: str, history: list[dict] = None) -> str:
    parts = []
    if context:
        parts.append(context)
    if history:
        for msg in history[-10:]:
            parts.append(f"{msg['role']}: {msg['content']}")
    parts.append(prompt)
    full_prompt = "\n\n".join(parts)
    try:
        response = await _gemini.generate_content_async(full_prompt)
        return response.text
    except Exception as e:
        return f"[Gemini Error] {e}"


async def _ask_claude(prompt: str, context: str, history: list[dict] = None) -> str:
    messages = []
    if history:
        for msg in history[-10:]:
            role = "user" if msg["role"] == "user" else "assistant"
            messages.append({"role": role, "content": msg["content"]})
    messages.append({"role": "user", "content": prompt})
    try:
        response = await _claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=context or "You are Byeol, a helpful AI assistant. Answer concisely.",
            messages=messages,
        )
        return response.content[0].text
    except Exception as e:
        return f"[Claude Error] {e}"


async def _ask_ollama(prompt: str, context: str, history: list[dict] = None, chat_id: int = 0) -> str:
    model = get_ollama_model(chat_id)
    if not model:
        return "[Ollama] 모델이 선택되지 않았습니다. /llm ollama 로 모델을 선택해주세요."
    messages = []
    system_msg = context or "You are Byeol, a helpful AI assistant. Answer concisely."
    messages.append({"role": "system", "content": system_msg})
    if history:
        for msg in history[-10:]:
            role = "user" if msg["role"] == "user" else "assistant"
            messages.append({"role": role, "content": msg["content"]})
    messages.append({"role": "user", "content": prompt})
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={"model": model, "messages": messages, "stream": False},
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return f"[Ollama Error] HTTP {resp.status}: {text}"
                data = await resp.json()
                return data["message"]["content"]
    except Exception as e:
        return f"[Ollama Error] {e}"
