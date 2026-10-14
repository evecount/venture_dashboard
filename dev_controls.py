"""
Developer controls: settings and commands written by the dashboard's Developer page (`bot_settings`,
`bot_commands`), and a copy of the bot's console output in `bot_logs` so it can be read without the VM.
Never raises: when the tables are missing the bot runs with its defaults.
"""

import sys
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

# Defaults when nothing is set in the Developer page.
DEFAULTS = {
    "paused": False,              # reply "back shortly" to everyone except developers
    "daily_checkin": True,        # 17:00 prompts and 09:30 nudges
    "channel_context": True,      # use channel memory when answering
    "ai_model": "",               # overrides AI_MODEL when set
    "extra_instructions": "",     # appended to the system prompt
}


class Settings:
    def __init__(self, sb):
        self.sb = sb
        self._cache = (0.0, {})

    def all(self) -> dict:
        stamp, values = self._cache
        if self.sb and time.time() - stamp > 15:
            try:
                rows = self.sb.table("bot_settings").select("key,value").execute().data or []
                values = {r["key"]: r["value"] for r in rows if r["key"] in DEFAULTS and r["value"] is not None}
            except Exception as e:  # noqa: BLE001
                print(f"[Settings Warning] {e}")
            self._cache = (time.time(), values)
        return {**DEFAULTS, **values}

    def get(self, key: str):
        return self.all().get(key, DEFAULTS.get(key))


class LogTee:
    """Wraps stdout: everything still prints, and complete lines are queued for `bot_logs`."""

    def __init__(self, stream, size: int = 500):
        self.stream, self.queue, self._buf = stream, deque(maxlen=size), ""
        self._lock = threading.Lock()

    def write(self, s):
        self.stream.write(s)
        with self._lock:
            self._buf += s
            *lines, self._buf = self._buf.split("\n")
            self.queue.extend(line[:2000] for line in lines if line.strip())
        return len(s)

    def flush(self):
        self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def drain(self) -> list:
        with self._lock:
            lines = list(self.queue)
            self.queue.clear()
        return lines


def install_log_tee() -> LogTee:
    tee = LogTee(sys.stdout)
    sys.stdout = tee
    return tee


def flush_logs(sb, tee: LogTee | None):
    """Writes queued console lines to `bot_logs`."""
    lines = tee.drain() if tee else []
    if not (sb and lines):
        return
    try:
        now = datetime.now(timezone.utc).isoformat()
        sb.table("bot_logs").insert([{"line": line, "created_at": now} for line in lines]).execute()
    except Exception as e:  # noqa: BLE001
        tee.stream.write(f"[Logs Warning] {e}\n")


def prune_logs(sb, days: int = 3):
    if sb:
        try:
            sb.table("bot_logs").delete().lt("created_at", (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()).execute()
        except Exception:  # noqa: BLE001
            pass


def run_commands(sb, handlers: dict):
    """Runs queued Developer-page commands one at a time. handlers: {name: fn(args, requested_by) -> str}."""
    if not sb:
        return
    try:
        queued = (sb.table("bot_commands").select("id,command,args,requested_by").eq("status", "queued")
                  .order("created_at").limit(5).execute().data or [])
    except Exception:  # noqa: BLE001 - table not created yet
        return
    for cmd in queued:
        claimed = (sb.table("bot_commands").update({"status": "running"}).eq("id", cmd["id"])
                   .eq("status", "queued").execute().data)
        if not claimed:
            continue
        fn = handlers.get(cmd["command"])
        try:
            result, status = (fn(cmd.get("args") or {}, cmd.get("requested_by")), "done") if fn else (
                f"Unknown command {cmd['command']}", "error")
        except Exception as e:  # noqa: BLE001
            result, status = f"{type(e).__name__}: {e}", "error"
        print(f"[Dev] {cmd['command']}: {status}")
        sb.table("bot_commands").update({"status": status, "result": str(result or "")[:20000],
                                         "finished_at": datetime.now(timezone.utc).isoformat()}).eq("id", cmd["id"]).execute()
