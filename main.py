import asyncio
import logging
import os
from datetime import time as dtime
from zoneinfo import ZoneInfo

from config import TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS, DEFAULT_LLM

LOCAL_TZ = ZoneInfo(os.environ.get("TZ", "UTC"))

from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    PicklePersistence,
    filters,
    ContextTypes,
)
from llm import ask, list_ollama_models
from search import web_search, fetch_page, fetch_rss, fetch_exchange_rate
from memory import memory
from agent import run_agent
from cron import add_job, remove_job, list_jobs, load_jobs, _parse_cron

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global ref to app for scheduling from agent
_app = None


def authorized(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if ALLOWED_USER_IDS and update.effective_user.id not in ALLOWED_USER_IDS:
            await update.message.reply_text("Unauthorized.")
            return
        return await func(update, context)
    return wrapper


# --- Cron execution ---

async def cron_execute(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id = job_data["chat_id"]

    # Read user's LLM preference from persistence
    user_data = context.application.user_data.get(chat_id, {})
    backend = user_data.get("backend", "")
    ollama_model = user_data.get("ollama_model", "")
    logger.info(f"Cron executing: {job_data['name']} | backend={backend} model={ollama_model} chat_id={chat_id}")

    if not backend:
        logger.warning(f"Cron {job_data['name']}: no LLM backend set for chat_id={chat_id}")
        text = f"[Scheduled: {job_data['name']}]\n\nLLM이 설정되지 않았습니다. /llm 으로 설정해주세요."
    elif job_data["action"].startswith("say:"):
        text = job_data["action"][4:].strip()
    elif job_data["action"].startswith("rss:"):
        rss_url = job_data["action"][4:].strip()
        entries = await asyncio.to_thread(fetch_rss, rss_url, 3)
        if not entries:
            text = f"[Scheduled: {job_data['name']}]\n\n피드를 가져올 수 없습니다."
        else:
            await context.bot.send_message(chat_id=chat_id, text=f"[Scheduled: {job_data['name']}]")
            for i, entry in enumerate(entries, 1):
                line = await _summarize_entry(i, entry, backend, ollama_model)
                await context.bot.send_message(chat_id=chat_id, text=line, disable_web_page_preview=True)
            return
    elif job_data["action"].startswith("exchange:"):
        # Format: "exchange:USD/KRW" or "exchange:" (default USD/KRW)
        pair = job_data["action"][9:].strip()
        parts = pair.split("/") if "/" in pair else pair.split()
        base = parts[0].upper() if len(parts) >= 1 and parts[0] else "USD"
        target = parts[1].upper() if len(parts) >= 2 else "KRW"
        result = await asyncio.to_thread(fetch_exchange_rate, base, target)
        if result["ok"]:
            rate = result["rate"]
            rate_str = f"{rate:,.2f}" if isinstance(rate, float) and rate >= 100 else str(rate)
            text = (
                f"[Scheduled: {job_data['name']}]\n\n"
                f"💱 1 {base} = {rate_str} {target}\n"
                f"📅 {result['date']}\n"
                f"🔗 https://www.investing.com/currencies/{base.lower()}-{target.lower()}"
            )
        else:
            text = f"[Scheduled: {job_data['name']}]\n\n환율 조회 실패: {result['error']}"
    elif job_data["action"].startswith("search:"):
        query = job_data["action"][7:]
        results = await asyncio.to_thread(web_search, query)
        text = f"[Scheduled: {job_data['name']}]\n\n"
        text += "\n\n".join(
            f"- {r['title']}\n  {r['url']}" for r in results
        )
    else:
        response = await run_agent(
            job_data["action"], chat_id,
            backend=backend, ollama_model=ollama_model,
        )
        text = f"[Scheduled: {job_data['name']}]\n\n{response}"

    await context.bot.send_message(chat_id=chat_id, text=text)


def schedule_job_to_queue(job_queue, job: dict):
    """Register a single job to telegram's JobQueue."""
    cron_parts = _parse_cron(job["cron"])

    # Convert APScheduler-style cron to telegram JobQueue
    # JobQueue doesn't support full cron, so we use run_daily/run_repeating
    minute = cron_parts["minute"]
    hour = cron_parts["hour"]
    day = cron_parts["day"]
    month = cron_parts["month"]
    dow = cron_parts["day_of_week"]

    # For simple daily jobs (specific hour:minute, every day)
    if day == "*" and month == "*":
        # Parse minute/hour - handle */N patterns
        if "/" in minute or "/" in hour:
            # Interval-based: use run_repeating
            if "/" in minute:
                interval_min = int(minute.split("/")[1])
                job_queue.run_repeating(
                    cron_execute,
                    interval=interval_min * 60,
                    first=10,
                    data=job,
                    name=job["name"],
                )
            elif "/" in hour:
                interval_hr = int(hour.split("/")[1])
                job_queue.run_repeating(
                    cron_execute,
                    interval=interval_hr * 3600,
                    first=10,
                    data=job,
                    name=job["name"],
                )
        else:
            # Specific time daily
            h = int(hour)
            m = int(minute)
            run_time = dtime(hour=h, minute=m, tzinfo=LOCAL_TZ)

            if dow == "*":
                # Every day
                job_queue.run_daily(
                    cron_execute,
                    time=run_time,
                    data=job,
                    name=job["name"],
                )
            else:
                # Specific days of week (0=Mon in telegram, 0=Mon in cron too)
                days = _parse_dow(dow)
                job_queue.run_daily(
                    cron_execute,
                    time=run_time,
                    days=days,
                    data=job,
                    name=job["name"],
                )

    logger.info(f"Scheduled: {job['name']} | {job['cron']} | {job['action']}")


def _parse_dow(dow_str: str) -> tuple:
    """Parse day_of_week string to tuple of ints (0=Mon..6=Sun)."""
    if dow_str == "*":
        return tuple(range(7))
    days = []
    for part in dow_str.split(","):
        if "-" in part:
            start, end = part.split("-")
            days.extend(range(int(start), int(end) + 1))
        else:
            days.append(int(part))
    return tuple(days)


def schedule_all_jobs(job_queue):
    """Load all saved jobs and register them. Only used at startup."""
    current_jobs = job_queue.jobs()
    for j in current_jobs:
        j.schedule_removal()

    for job in load_jobs():
        try:
            schedule_job_to_queue(job_queue, job)
        except Exception as e:
            logger.error(f"Failed to schedule {job['name']}: {e}")


def add_job_to_queue(job_queue, job: dict):
    """Add a single job without touching other jobs."""
    # Remove only this specific job if it exists
    for j in job_queue.jobs():
        if j.name == job["name"]:
            j.schedule_removal()
            break
    try:
        schedule_job_to_queue(job_queue, job)
    except Exception as e:
        logger.error(f"Failed to schedule {job['name']}: {e}")


def remove_job_from_queue(job_queue, name: str):
    """Remove a single job without touching other jobs."""
    for j in job_queue.jobs():
        if j.name == name:
            j.schedule_removal()
            logger.info(f"Unscheduled: {name}")
            return


# --- Handlers ---

@authorized
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Byeol - Your Personal Assistant & Coach\n\n"
        "Just talk to me naturally. I'll remember everything.\n\n"
        "Commands:\n"
        "/search <query> - Web search\n"
        "/read <url> - Read & summarize page\n"
        "/exchange [base] [target] - Exchange rate (default: USD KRW)\n"
        "/goals - Show active goals\n"
        "/journal - Show recent journal\n"
        "/profile - Show what I know about you\n"
        "/cron add <name> <cron> <action> - Schedule task\n"
        "/cron rm <name> | /cron list\n"
        "/mem list | /mem set <k> <v> | /mem del <k>\n"
        "/clear - Clear chat history\n"
        "/rss <feed_url> - RSS feed summary\n"
        "/llm <gemini|claude|ollama> - Switch LLM\n"
    )


@authorized
async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("Usage: /search <query>")
        return
    await update.message.reply_text(f"Searching: {query}")
    results = await asyncio.to_thread(web_search, query)
    if not results:
        await update.message.reply_text("No results found.")
        return
    text = "\n\n".join(
        f"*{r['title']}*\n{r['url']}\n{r['snippet']}" for r in results
    )
    await update.message.reply_text(text, parse_mode="Markdown")


@authorized
async def cmd_read(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = context.args[0] if context.args else ""
    if not url:
        await update.message.reply_text("Usage: /read <url>")
        return
    await update.message.reply_text("Reading page...")
    chat_id = update.effective_chat.id
    backend = _get_backend(context)
    content = await asyncio.to_thread(fetch_page, url)
    history = memory.get_history(chat_id)
    summary = await ask(
        f"Summarize the following page content in Korean:\n\n{content}",
        backend=backend,
        history=history,
        ollama_model=context.user_data.get("ollama_model", ""),
    )
    await update.message.reply_text(summary)


@authorized
async def cmd_rss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = context.args[0] if context.args else ""
    if not url:
        await update.message.reply_text("Usage: /rss <feed_url>")
        return
    await update.message.reply_text("Reading feed...")
    backend = _get_backend(context)
    ollama_model = context.user_data.get("ollama_model", "")
    entries = await asyncio.to_thread(fetch_rss, url, 3)
    if not entries:
        await update.message.reply_text("피드를 가져올 수 없습니다. URL을 확인해주세요.")
        return
    for i, entry in enumerate(entries, 1):
        line = await _summarize_entry(i, entry, backend, ollama_model)
        await update.message.reply_text(line, disable_web_page_preview=True)


@authorized
async def cmd_exchange(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    base = args[0].upper() if len(args) >= 1 else "USD"
    target = args[1].upper() if len(args) >= 2 else "KRW"
    result = await asyncio.to_thread(fetch_exchange_rate, base, target)
    if result["ok"]:
        rate = result["rate"]
        # Format with comma separator
        if isinstance(rate, float) and rate >= 100:
            rate_str = f"{rate:,.2f}"
        else:
            rate_str = str(rate)
        await update.message.reply_text(
            f"💱 1 {base} = {rate_str} {target}\n"
            f"📅 {result['date']}\n"
            f"🔗 https://www.investing.com/currencies/{base.lower()}-{target.lower()}"
        )
    else:
        await update.message.reply_text(f"환율 조회 실패: {result['error']}")


async def _summarize_entry(idx: int, entry: dict, backend: str, ollama_model: str) -> str:
    """Summarize a single RSS entry with LLM."""
    try:
        summary = await ask(
            f"You are summarizing an RSS article. The title is already shown to the user, "
            f"so DO NOT repeat it. Instead, explain WHY this matters or WHAT the key detail is "
            f"that the title doesn't tell you. One short Korean sentence (under 80 chars). "
            f"Add one relevant emoji at the end.\n\n"
            f"Title: {entry['title']}\n"
            f"Content: {entry['summary']}",
            backend=backend,
            ollama_model=ollama_model,
        )
        summary = summary.strip().strip('"').strip()
        if summary.startswith("[") and "Error]" in summary:
            return f"{idx}. {entry['title']} 👉 {entry['link']}"
        return f"{idx}. {entry['title']} – {summary} 👉 {entry['link']}"
    except Exception:
        return f"{idx}. {entry['title']} 👉 {entry['link']}"



@authorized
async def cmd_cron(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage:\n"
            "/cron add <name> <min> <hour> <day> <month> <dow> <action>\n"
            "/cron rm <name>\n"
            "/cron list"
        )
        return

    sub = args[0]

    if sub == "list":
        jobs = list_jobs()
        if not jobs:
            await update.message.reply_text("No scheduled jobs.")
            return
        text = "\n".join(
            f"- {j['name']} | {j['cron']} | {j['action']}" for j in jobs
        )
        await update.message.reply_text(text)

    elif sub == "rm" and len(args) >= 2:
        if remove_job(args[1]):
            remove_job_from_queue(context.application.job_queue, args[1])
            await update.message.reply_text(f"Removed: {args[1]}")
        else:
            await update.message.reply_text(f"Not found: {args[1]}")

    elif sub == "add" and len(args) >= 8:
        name = args[1]
        cron_expr = " ".join(args[2:7])
        action = " ".join(args[7:])
        try:
            job = add_job(name, cron_expr, action, update.effective_chat.id)
            add_job_to_queue(context.application.job_queue, job)
            await update.message.reply_text(
                f"Added: {job['name']}\nCron: {job['cron']}\nAction: {job['action']}"
            )
        except ValueError as e:
            await update.message.reply_text(f"Error: {e}")
    else:
        await update.message.reply_text("Invalid cron command. See /cron for usage.")


@authorized
async def cmd_mem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage:\n/mem list\n/mem set <key> <value>\n/mem del <key>"
        )
        return

    sub = args[0]

    if sub == "list":
        store = memory.recall_all()
        if not store:
            await update.message.reply_text("No stored memories.")
            return
        text = "\n".join(f"- {k}: {v}" for k, v in store.items())
        await update.message.reply_text(text)

    elif sub == "set" and len(args) >= 3:
        key = args[1]
        value = " ".join(args[2:])
        memory.remember(key, value)
        await update.message.reply_text(f"Saved: {key} = {value}")

    elif sub == "del" and len(args) >= 2:
        if memory.forget(args[1]):
            await update.message.reply_text(f"Deleted: {args[1]}")
        else:
            await update.message.reply_text(f"Not found: {args[1]}")
    else:
        await update.message.reply_text("Invalid mem command.")


@authorized
async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    memory.clear_history(update.effective_chat.id)
    await update.message.reply_text("Chat history cleared.")


@authorized
async def cmd_goals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    goals = memory.get_goals(active_only=False)
    if not goals:
        await update.message.reply_text("No goals yet. Tell me what you want to achieve!")
        return
    lines = []
    for g in goals:
        status = "done" if g["status"] == "completed" else "active"
        line = f"[{status}] #{g['id']} {g['title']}"
        if g.get("deadline"):
            line += f" (by {g['deadline']})"
        if g.get("progress"):
            line += f"\n  last: {g['progress'][-1]['note']}"
        lines.append(line)
    await update.message.reply_text("\n\n".join(lines))


@authorized
async def cmd_journal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    entries = memory.get_journal(7)
    if not entries:
        await update.message.reply_text("No journal entries yet. Tell me about your day!")
        return
    lines = []
    for e in entries:
        mood = f" ({e['mood']})" if e.get("mood") else ""
        lines.append(f"{e['date'][:10]}{mood}: {e['content']}")
    await update.message.reply_text("\n\n".join(lines))


@authorized
async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = memory.get_profile()
    if not profile:
        await update.message.reply_text("I don't know much about you yet. Let's chat!")
        return
    text = "\n".join(f"- {k}: {v}" for k, v in profile.items())
    await update.message.reply_text(f"What I know about you:\n\n{text}")


@authorized
async def cmd_llm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []

    # No args → show picker with all backends
    if not args:
        buttons = [
            [InlineKeyboardButton("Gemini", callback_data="llm:gemini"),
             InlineKeyboardButton("Claude", callback_data="llm:claude"),
             InlineKeyboardButton("Ollama →", callback_data="llm:ollama_pick")],
        ]
        current = _get_backend(context)
        extra = ""
        if current == "ollama":
            extra = f" ({context.user_data.get('ollama_model', 'not set')})"
        await update.message.reply_text(
            f"Current: {current}{extra}\nSelect LLM:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    backend = args[0]
    if backend not in ("gemini", "claude", "ollama"):
        await update.message.reply_text("Usage: /llm [gemini|claude|ollama]")
        return
    if backend == "ollama":
        await _show_ollama_models(update.message, context.user_data.get("ollama_model", ""))
        return
    context.user_data["backend"] = backend
    await update.message.reply_text(f"LLM switched to: {backend}")


async def _show_ollama_models(message, current_model: str = ""):
    """Fetch Ollama models and show as inline buttons."""
    models = await list_ollama_models()
    if not models:
        await message.reply_text("Ollama 서버에 연결할 수 없거나 모델이 없습니다.")
        return
    current = current_model
    buttons = []
    row = []
    for m in models:
        label = f"✓ {m}" if m == current else m
        row.append(InlineKeyboardButton(label, callback_data=f"ollama_model:{m}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    await message.reply_text(
        "Ollama 모델 선택:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def handle_llm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Auth check
    if ALLOWED_USER_IDS and query.from_user.id not in ALLOWED_USER_IDS:
        await query.answer("Unauthorized.")
        return

    data = query.data
    await query.answer()

    if data == "llm:gemini":
        context.user_data["backend"] = "gemini"
        await query.edit_message_text("LLM switched to: gemini")
    elif data == "llm:claude":
        context.user_data["backend"] = "claude"
        await query.edit_message_text("LLM switched to: claude")
    elif data == "llm:ollama_pick":
        await _show_ollama_models(query.message, context.user_data.get("ollama_model", ""))
    elif data.startswith("ollama_model:"):
        model = data.split(":", 1)[1]
        context.user_data["ollama_model"] = model
        context.user_data["backend"] = "ollama"
        await query.edit_message_text(f"LLM switched to: ollama ({model})")


@authorized
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    chat_id = update.effective_chat.id
    backend = _get_backend(context)

    memory.add_message(chat_id, "user", user_msg)
    await update.message.reply_text("Thinking...")

    jq = context.application.job_queue

    def _cron_add(job: dict):
        add_job_to_queue(jq, job)

    def _cron_remove(name: str):
        remove_job_from_queue(jq, name)

    ollama_model = context.user_data.get("ollama_model", "")
    try:
        response = await run_agent(
            user_msg, chat_id, backend=backend, ollama_model=ollama_model,
            cron_on_add=_cron_add, cron_on_remove=_cron_remove,
        )
    except Exception as e:
        logger.error(f"Agent error: {e}")
        response = f"오류가 발생했습니다: {e}"

    memory.add_message(chat_id, "assistant", response)
    for i in range(0, len(response), 4000):
        await update.message.reply_text(response[i:i + 4000])


def _get_backend(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("backend", DEFAULT_LLM)


# --- Main ---

def main():
    global _app
    persistence = PicklePersistence(filepath="bot_data.pickle")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).persistence(persistence).build()
    _app = app

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("read", cmd_read))
    app.add_handler(CommandHandler("rss", cmd_rss))
    app.add_handler(CommandHandler("exchange", cmd_exchange))
    app.add_handler(CommandHandler("cron", cmd_cron))
    app.add_handler(CommandHandler("mem", cmd_mem))
    app.add_handler(CommandHandler("goals", cmd_goals))
    app.add_handler(CommandHandler("journal", cmd_journal))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("llm", cmd_llm))
    app.add_handler(CallbackQueryHandler(handle_llm_callback, pattern=r"^(llm:|ollama_model:)"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Schedule saved cron jobs
    schedule_all_jobs(app.job_queue)

    logger.info("Byeol agent started.")
    app.run_polling()


if __name__ == "__main__":
    main()
