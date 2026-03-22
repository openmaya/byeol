import json
import os
import logging

JOBS_FILE = os.path.join(os.path.dirname(__file__), "jobs.json")
logger = logging.getLogger(__name__)


def load_jobs() -> list[dict]:
    if not os.path.exists(JOBS_FILE):
        return []
    with open(JOBS_FILE, "r") as f:
        return json.load(f)


def save_jobs(jobs: list[dict]):
    with open(JOBS_FILE, "w") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)


def add_job(name: str, cron_expr: str, action: str, chat_id: int,
            backend: str = "", ollama_model: str = "") -> dict:
    """Add a cron job. cron_expr format: 'minute hour day month day_of_week'"""
    cron_expr = cron_expr.strip().strip("'\"")
    parts = cron_expr.split()
    if len(parts) != 5:
        raise ValueError("Cron format: 'minute hour day month day_of_week'")

    job = {
        "name": name,
        "cron": cron_expr,
        "action": action,
        "chat_id": chat_id,
        "backend": backend,
        "ollama_model": ollama_model,
    }
    jobs = load_jobs()
    jobs = [j for j in jobs if j["name"] != name]
    jobs.append(job)
    save_jobs(jobs)
    return job


def remove_job(name: str) -> bool:
    jobs = load_jobs()
    filtered = [j for j in jobs if j["name"] != name]
    if len(filtered) == len(jobs):
        return False
    save_jobs(filtered)
    return True


def list_jobs() -> list[dict]:
    return load_jobs()


def _parse_cron(cron_expr: str) -> dict:
    """Parse '10 8 * * *' into kwargs for APScheduler CronTrigger."""
    parts = cron_expr.strip().split()
    return {
        "minute": parts[0],
        "hour": parts[1],
        "day": parts[2],
        "month": parts[3],
        "day_of_week": parts[4],
    }
