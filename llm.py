import google.generativeai as genai
import anthropic
from config import GOOGLE_API_KEY, ANTHROPIC_API_KEY

# --- Gemini ---
genai.configure(api_key=GOOGLE_API_KEY)
_gemini = genai.GenerativeModel("gemini-2.5-flash")

# --- Claude ---
_claude = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

DEFAULT_BACKEND = "gemini"


async def ask(prompt: str, context: str = "", backend: str = "", history: list[dict] = None) -> str:
    backend = backend or DEFAULT_BACKEND

    if backend == "claude" and _claude:
        return await _ask_claude(prompt, context, history)
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
