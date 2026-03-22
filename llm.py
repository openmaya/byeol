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


async def ask(prompt: str, context: str = "", backend: str = "", history: list[dict] = None, ollama_model: str = "") -> str:
    backend = backend or DEFAULT_BACKEND

    if backend == "claude" and _claude:
        return await _ask_claude(prompt, context, history)
    if backend == "ollama":
        return await _ask_ollama(prompt, context, history, model=ollama_model)
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


async def _ask_ollama(prompt: str, context: str, history: list[dict] = None, model: str = "") -> str:
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
        import logging
        logging.getLogger(__name__).error(f"Ollama request failed: {type(e).__name__}: {e!r} | model={model} url={OLLAMA_BASE_URL}")
        return f"[Ollama Error] {type(e).__name__}: {e}"
