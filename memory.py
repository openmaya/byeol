import json
import os
from datetime import datetime
from collections import deque

MEMORY_FILE = os.path.join(os.path.dirname(__file__), "memory.json")
MAX_HISTORY = 30


class Memory:
    def __init__(self):
        self._history: dict[int, deque] = {}
        self._store: dict[str, str] = {}
        self._profile: dict[str, str] = {}
        self._goals: list[dict] = []
        self._journal: list[dict] = []
        self._load()

    def _load(self):
        if not os.path.exists(MEMORY_FILE):
            return
        with open(MEMORY_FILE, "r") as f:
            data = json.load(f)
        self._store = data.get("store", {})
        self._profile = data.get("profile", {})
        self._goals = data.get("goals", [])
        self._journal = data.get("journal", [])
        for chat_id, msgs in data.get("history", {}).items():
            self._history[int(chat_id)] = deque(msgs, maxlen=MAX_HISTORY)

    def _save(self):
        data = {
            "store": self._store,
            "profile": self._profile,
            "goals": self._goals,
            "journal": self._journal,
            "history": {
                str(k): list(v) for k, v in self._history.items()
            },
        }
        with open(MEMORY_FILE, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # --- Conversation history ---

    def add_message(self, chat_id: int, role: str, content: str):
        if chat_id not in self._history:
            self._history[chat_id] = deque(maxlen=MAX_HISTORY)
        self._history[chat_id].append({
            "role": role,
            "content": content,
            "time": datetime.now().isoformat(),
        })
        self._save()

    def get_history(self, chat_id: int) -> list[dict]:
        return list(self._history.get(chat_id, []))

    def clear_history(self, chat_id: int):
        self._history.pop(chat_id, None)
        self._save()

    # --- Key-value memory ---

    def remember(self, key: str, value: str):
        self._store[key] = value
        self._save()

    def recall(self, key: str) -> str | None:
        return self._store.get(key)

    def forget(self, key: str) -> bool:
        if key in self._store:
            del self._store[key]
            self._save()
            return True
        return False

    def recall_all(self) -> dict[str, str]:
        return dict(self._store)

    # --- User profile (auto-learned) ---

    def update_profile(self, key: str, value: str):
        self._profile[key] = value
        self._save()

    def get_profile(self) -> dict[str, str]:
        return dict(self._profile)

    # --- Goals ---

    def add_goal(self, title: str, details: str = "", deadline: str = "") -> dict:
        goal = {
            "id": len(self._goals) + 1,
            "title": title,
            "details": details,
            "deadline": deadline,
            "status": "active",
            "progress": [],
            "created": datetime.now().isoformat(),
        }
        self._goals.append(goal)
        self._save()
        return goal

    def update_goal_progress(self, goal_id: int, note: str):
        for goal in self._goals:
            if goal["id"] == goal_id:
                goal["progress"].append({
                    "note": note,
                    "date": datetime.now().isoformat(),
                })
                self._save()
                return True
        return False

    def complete_goal(self, goal_id: int) -> bool:
        for goal in self._goals:
            if goal["id"] == goal_id:
                goal["status"] = "completed"
                self._save()
                return True
        return False

    def get_goals(self, active_only: bool = True) -> list[dict]:
        if active_only:
            return [g for g in self._goals if g["status"] == "active"]
        return list(self._goals)

    # --- Journal (daily log) ---

    def add_journal(self, content: str, mood: str = ""):
        entry = {
            "content": content,
            "mood": mood,
            "date": datetime.now().isoformat(),
        }
        self._journal.append(entry)
        self._save()

    def get_journal(self, last_n: int = 7) -> list[dict]:
        return self._journal[-last_n:]

    # --- Summary for agent context ---

    def get_full_context(self) -> str:
        parts = []

        profile = self.get_profile()
        if profile:
            parts.append("== User Profile ==")
            parts.extend(f"- {k}: {v}" for k, v in profile.items())

        goals = self.get_goals()
        if goals:
            parts.append("\n== Active Goals ==")
            for g in goals:
                line = f"- [{g['id']}] {g['title']}"
                if g["deadline"]:
                    line += f" (deadline: {g['deadline']})"
                if g["progress"]:
                    last = g["progress"][-1]
                    line += f" | last update: {last['note']}"
                parts.append(line)

        journal = self.get_journal(3)
        if journal:
            parts.append("\n== Recent Journal ==")
            for j in journal:
                mood = f" ({j['mood']})" if j.get("mood") else ""
                parts.append(f"- {j['date'][:10]}{mood}: {j['content']}")

        store = self.recall_all()
        if store:
            parts.append("\n== Stored Memories ==")
            parts.extend(f"- {k}: {v}" for k, v in store.items())

        return "\n".join(parts)


memory = Memory()
