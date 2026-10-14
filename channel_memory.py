"""
Channel memory: the bot reads only the Slack channels switched on in the dashboard's Developer page, keeps the
last 7 days of their messages (`channel_messages`) and forgets anything older.

Privacy: when someone asks the bot a question, it only sees messages from enabled channels that person is a
member of in Slack, so the bot never reveals a channel to someone who couldn't read it themselves.
Every method swallows and logs errors, so a missing table or a missing Slack scope never breaks a conversation.
"""

import re
import time
from datetime import datetime, timedelta, timezone

WINDOW_DAYS = 7
MAX_CONTEXT_CHARS = 40000
SGT = timezone(timedelta(hours=8))
# Scopes needed to read channels (channels:join only to join public channels without an invite).
NEEDED_SCOPES = ("channels:read", "channels:history", "groups:read", "groups:history", "users:read")
OPTIONAL_SCOPES = ("channels:join",)

_MENTION = re.compile(r"<@([UW][A-Z0-9]+)(?:\|[^>]*)?>")
_CHANNEL = re.compile(r"<#[CG][A-Z0-9]+\|([^>]*)>")
_LINK = re.compile(r"<(https?://[^>|]+)(?:\|([^>]*))?>")


def clean_text(text: str, names: dict) -> str:
    """Slack markup to plain text: <@U1> -> @Name, <#C1|general> -> #general, <url|label> -> label (url)."""
    text = _MENTION.sub(lambda m: "@" + names.get(m.group(1), "someone"), text or "")
    text = _CHANNEL.sub(lambda m: "#" + m.group(1), text)
    text = _LINK.sub(lambda m: f"{m.group(2)} ({m.group(1)})" if m.group(2) else m.group(1), text)
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").strip()


def ts_to_dt(ts: str) -> datetime:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc)


def format_context(channels: dict, messages: list, max_chars: int = MAX_CONTEXT_CHARS) -> str:
    """
    channels: {id: name}; messages: rows newest first. Keeps the newest messages that fit in max_chars and
    prints them per channel, oldest first, with thread replies marked. Returns "" when there is nothing.
    """
    kept, size = [], 0
    for m in messages:
        line = (f"{ts_to_dt(m['ts']).astimezone(SGT).strftime('%a %d %b %H:%M')} · "
                f"{m.get('user_name') or 'someone'}: {(m.get('text') or '').replace(chr(10), ' / ')}")
        if m.get("thread_ts") and m["thread_ts"] != m["ts"]:
            line = "  ↳ " + line
        if size + len(line) > max_chars:
            break
        kept.append((m, line))
        size += len(line) + 1
    if not kept:
        return ""
    out = []
    for cid, name in channels.items():
        rows = [(m, line) for m, line in kept if m["channel_id"] == cid]
        if not rows:
            continue
        # Threads stay under their parent: sort by (thread root, ts).
        rows.sort(key=lambda r: (float(r[0].get("thread_ts") or r[0]["ts"]), float(r[0]["ts"])))
        out.append(f"#{name}:")
        out += [line for _, line in rows]
    return "\n".join(out)


class ChannelMemory:
    def __init__(self, sb, client=None):
        self.sb, self.client = sb, client
        self._enabled = (0.0, set())
        self._names: dict = {}

    def _guard(self, label, fn, default=None):
        if not self.sb:
            return default
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - channel memory must never break the bot
            print(f"[Channels Warning] {label}: {e}")
            return default

    # --- which channels ---
    def enabled_ids(self) -> set:
        stamp, ids = self._enabled
        if time.time() - stamp > 15:
            rows = self._guard("enabled", lambda: self.sb.table("bot_channels").select("id").eq("enabled", True).execute().data)
            ids = {r["id"] for r in rows or []} if rows is not None else ids
            self._enabled = (time.time(), ids)
        return ids

    def forget_cache(self):
        self._enabled = (0.0, set())

    def user_name(self, user_id: str | None) -> str:
        if not user_id:
            return "someone"
        if user_id not in self._names:
            name = user_id
            try:
                p = self.client.users_info(user=user_id)["user"]
                name = (p.get("profile") or {}).get("display_name") or p.get("real_name") or p.get("name") or user_id
            except Exception as e:  # noqa: BLE001
                print(f"[Channels Warning] user name {user_id}: {e}")
            self._names[user_id] = name
        return self._names[user_id]

    def _names_in(self, text: str) -> dict:
        return {uid: self.user_name(uid) for uid in set(_MENTION.findall(text or ""))}

    def _row(self, channel_id: str, msg: dict) -> dict | None:
        text = msg.get("text") or ""
        if not text.strip() or msg.get("subtype") in ("channel_join", "channel_leave", "message_deleted"):
            return None
        who = msg.get("user")
        name = self.user_name(who) if who else ((msg.get("bot_profile") or {}).get("name") or msg.get("username") or "a bot")
        return {"channel_id": channel_id, "ts": msg["ts"], "thread_ts": msg.get("thread_ts"), "user_id": who,
                "user_name": name, "text": clean_text(text, self._names_in(text))[:4000],
                "posted_at": ts_to_dt(msg["ts"]).isoformat()}

    # --- live events ---
    def ingest(self, event: dict) -> bool:
        """Stores a channel message if its channel is enabled. Returns True when stored."""
        channel = event.get("channel")
        if not channel or channel not in self.enabled_ids():
            return False
        row = self._row(channel, event)
        if not row:
            return False
        return bool(self._guard("ingest", lambda: self.sb.table("channel_messages").upsert(row).execute() or True, False))

    def edited(self, event: dict):
        msg, channel = event.get("message") or {}, event.get("channel")
        if channel in self.enabled_ids() and msg.get("ts"):
            text = msg.get("text") or ""
            self._guard("edit", lambda: self.sb.table("channel_messages").update(
                {"text": clean_text(text, self._names_in(text))[:4000]}).eq("channel_id", channel).eq("ts", msg["ts"]).execute())

    def deleted(self, event: dict):
        ts = event.get("deleted_ts") or (event.get("previous_message") or {}).get("ts")
        if event.get("channel") and ts:
            self._guard("delete", lambda: self.sb.table("channel_messages").delete()
                        .eq("channel_id", event["channel"]).eq("ts", ts).execute())

    def members_changed(self, channel: str):
        """Keeps the 'who may ask about this channel' list current as people join or leave."""
        if channel in self.enabled_ids():
            self._guard("members", lambda: self.refresh_members(channel))

    # --- syncing with Slack ---
    def refresh_list(self) -> str:
        """Upserts every channel the bot can see (does not change which are enabled)."""
        found, cursor = [], None
        try:
            while True:
                res = self.client.conversations_list(types="public_channel,private_channel", exclude_archived=True,
                                                     limit=200, cursor=cursor)
                found += res.get("channels") or []
                cursor = (res.get("response_metadata") or {}).get("next_cursor")
                if not cursor:
                    break
        except Exception as e:  # noqa: BLE001
            return f"Couldn't list channels: {e}"
        now = datetime.now(timezone.utc).isoformat()
        rows = [{"id": c["id"], "name": c.get("name") or c["id"], "is_private": bool(c.get("is_private")),
                 "is_member": bool(c.get("is_member")), "num_members": c.get("num_members"), "updated_at": now}
                for c in found]
        if rows:
            self._guard("list", lambda: self.sb.table("bot_channels").upsert(rows).execute())
        return f"Found {len(rows)} channels."

    def refresh_members(self, channel_id: str) -> list:
        ids, cursor = [], None
        while True:
            res = self.client.conversations_members(channel=channel_id, limit=500, cursor=cursor)
            ids += res.get("members") or []
            cursor = (res.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break
        self._guard("members", lambda: self.sb.table("bot_channels").update(
            {"member_ids": ids, "num_members": len(ids)}).eq("id", channel_id).execute())
        return ids

    def _status(self, channel_id: str, status: str, **extra):
        self._guard("status", lambda: self.sb.table("bot_channels").update(
            {"status": status[:300], "updated_at": datetime.now(timezone.utc).isoformat(), **extra}).eq("id", channel_id).execute())

    def activate(self, channel_id: str) -> str:
        """Joins (public channels), records members and reads the last 7 days, including thread replies."""
        self.forget_cache()
        try:
            info = self.client.conversations_info(channel=channel_id)["channel"]
            if not info.get("is_member"):
                if info.get("is_private"):
                    msg = "Private channel: invite the bot first (/invite @Venture Buddy), then press Sync."
                    self._status(channel_id, msg, is_member=False)
                    return msg
                self.client.conversations_join(channel=channel_id)
            self.refresh_members(channel_id)
            oldest = str((datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).timestamp())
            rows, cursor, threads = [], None, []
            while True:
                res = self.client.conversations_history(channel=channel_id, oldest=oldest, limit=200, cursor=cursor)
                for m in res.get("messages") or []:
                    row = self._row(channel_id, m)
                    if row:
                        rows.append(row)
                    if m.get("reply_count"):
                        threads.append(m["ts"])
                cursor = (res.get("response_metadata") or {}).get("next_cursor")
                if not cursor:
                    break
            for root in threads[:100]:
                res = self.client.conversations_replies(channel=channel_id, ts=root, oldest=oldest, limit=200)
                rows += [r for r in (self._row(channel_id, m) for m in (res.get("messages") or [])[1:]) if r]
            for i in range(0, len(rows), 200):
                self.sb.table("channel_messages").upsert(rows[i:i + 200]).execute()
            msg = f"Reading. Loaded {len(rows)} messages from the last {WINDOW_DAYS} days."
            self._status(channel_id, msg, is_member=True, backfilled_at=datetime.now(timezone.utc).isoformat())
            return msg
        except Exception as e:  # noqa: BLE001
            err = getattr(getattr(e, "response", None), "data", {}) or {}
            reason = err.get("error") if isinstance(err, dict) else None
            msg = {"missing_scope": f"Missing Slack scope ({err.get('needed', '?')}). Add it on the Slack app page and reinstall.",
                   "not_in_channel": "The bot isn't in this channel. Invite it, then press Sync.",
                   "channel_not_found": "Slack can't find this channel for the bot. Invite it, then press Sync."}.get(
                reason or "", f"Sync failed: {reason or e}")
            self._status(channel_id, msg)
            return msg

    def prune(self) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).isoformat()
        rows = self._guard("prune", lambda: self.sb.table("channel_messages").delete().lt("posted_at", cutoff).execute().data, [])
        return len(rows or [])

    # --- what the agent sees ---
    def context_for(self, slack_user_id: str, max_chars: int = MAX_CONTEXT_CHARS) -> str:
        """Last 7 days from enabled channels this person is a member of; "" when there are none."""
        def run():
            chans = (self.sb.table("bot_channels").select("id,name").eq("enabled", True)
                     .contains("member_ids", [slack_user_id]).order("name").execute().data or [])
            if not chans:
                return ""
            cutoff = (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).isoformat()
            msgs = (self.sb.table("channel_messages").select("channel_id,ts,thread_ts,user_name,text")
                    .in_("channel_id", [c["id"] for c in chans]).gte("posted_at", cutoff)
                    .order("posted_at", desc=True).limit(2000).execute().data or [])
            return format_context({c["id"]: c["name"] for c in chans}, msgs, max_chars)
        return self._guard("context", run, "")
