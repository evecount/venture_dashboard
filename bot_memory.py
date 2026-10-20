"""
Persistent memory + CRM data access for the Slack bot (Supabase, service-role only).

Every method swallows and logs database errors and returns an empty/False result, so a missing
table or an outage degrades the bot to "no memory" instead of crashing a conversation.
"""

from datetime import datetime, timezone


class Memory:
    def __init__(self, sb):
        self.sb = sb

    def _guard(self, label, fn, default):
        if not self.sb:
            return default
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - deliberate: memory must never break the bot
            print(f"[Memory Warning] {label}: {e}")
            return default

    # --- short-term: conversation history ---
    def history(self, slack_user_id: str, limit: int = 12) -> list:
        def run():
            rows = (
                self.sb.table("bot_messages").select("role,content")
                .eq("slack_user_id", slack_user_id)
                .order("created_at", desc=True).limit(limit).execute().data
            )
            return [{"role": r["role"], "content": r["content"]} for r in reversed(rows or [])]
        return self._guard("history", run, [])

    def log(self, slack_user_id: str, role: str, content: str):
        if not content:
            return
        self._guard("log", lambda: self.sb.table("bot_messages").insert(
            {"slack_user_id": slack_user_id, "role": role, "content": content[:4000]}).execute(), None)

    # --- long-term: facts ---
    def remember(self, subject_type: str, subject_id: str, fact: str, audience: str, created_by: str) -> bool:
        def run():
            existing = self.sb.table("memories").select("id").eq("subject_id", subject_id).eq("fact", fact).execute().data
            if existing:
                return True
            self.sb.table("memories").insert({
                "subject_type": subject_type, "subject_id": subject_id, "fact": fact[:500],
                "audience": audience, "created_by": created_by,
            }).execute()
            return True
        return self._guard("remember", run, False)

    def facts(self, subject_ids: list, audience_all_only: bool, limit: int = 25) -> list:
        """Returns [{'subject_id', 'fact'}] newest first."""
        def run():
            q = self.sb.table("memories").select("subject_id,fact,audience").in_("subject_id", subject_ids)
            if audience_all_only:
                q = q.eq("audience", "all")
            return q.order("created_at", desc=True).limit(limit).execute().data or []
        return self._guard("facts", run, []) if subject_ids else []

    def recent_facts(self, limit: int = 25) -> list:
        """Mentor view: newest facts across the whole cohort."""
        return self._guard("recent_facts", lambda: self.sb.table("memories").select("subject_id,fact,audience")
                           .not_.in_("subject_type", ["digest_prefs", "behavior", "feature_request"])  # preferences aren't facts
                           .order("created_at", desc=True).limit(limit).execute().data or [], [])

    # --- CRM: notes ---
    def add_note(self, startup_id: str, author_slack_id: str, author_name: str, body: str) -> bool:
        return self._guard("add_note", lambda: bool(self.sb.table("notes").insert({
            "startup_id": startup_id, "author_slack_id": author_slack_id,
            "author_name": author_name, "body": body[:2000]}).execute()), False)

    def recent_notes(self, startup_id: str | None = None, limit: int = 10) -> list:
        def run():
            q = self.sb.table("notes").select("startup_id,author_name,body,created_at,startups(name)")
            if startup_id:
                q = q.eq("startup_id", startup_id)
            return q.order("created_at", desc=True).limit(limit).execute().data or []
        return self._guard("recent_notes", run, [])

    # --- CRM: tasks ---
    def add_task(self, startup_id: str | None, owner_slack_id: str | None, title: str,
                 due_date: str | None, created_by: str) -> bool:
        return self._guard("add_task", lambda: bool(self.sb.table("tasks").insert({
            "startup_id": startup_id, "owner_slack_id": owner_slack_id, "title": title[:300],
            "due_date": due_date, "created_by": created_by}).execute()), False)

    def open_tasks(self, startup_id: str | None = None, limit: int = 30) -> list:
        def run():
            q = self.sb.table("tasks").select("id,startup_id,owner_slack_id,title,due_date,created_by,startups(name)").eq("status", "open")
            if startup_id:
                q = q.eq("startup_id", startup_id)
            return q.order("due_date", desc=False, nullsfirst=False).limit(limit).execute().data or []
        return self._guard("open_tasks", run, [])

    def founder_tasks(self, startup_id: str, limit: int = 30) -> list:
        """Open tasks a founder may see: unowned ones and their team's own, never a mentor's private follow-ups."""
        tasks = self.open_tasks(startup_id, limit)
        if not any(t.get("owner_slack_id") for t in tasks):
            return tasks
        team = {f["slack_user_id"] for f in self._guard("team", lambda: self.sb.table("founders").select("slack_user_id")
                .eq("startup_id", startup_id).execute().data or [], []) if f.get("slack_user_id")}
        return [t for t in tasks if not t.get("owner_slack_id") or t["owner_slack_id"] in team]

    def complete_task(self, task_id: str) -> bool:
        return self._guard("complete_task", lambda: bool(self.sb.table("tasks").update({
            "status": "done", "completed_at": datetime.now(timezone.utc).isoformat()}).eq("id", task_id).execute()), False)

    # --- milestones & goals ---
    def add_milestone(self, startup_id: str, title: str, due_date: str | None, created_by: str, role: str) -> str | None:
        def run():
            res = self.sb.table("milestones").insert({
                "startup_id": startup_id, "title": title[:200], "due_date": due_date,
                "created_by": created_by, "created_by_role": role}).execute()
            return res.data[0]["id"] if res.data else None
        return self._guard("add_milestone", run, None)

    def milestones(self, startup_id: str | None = None, limit: int = 40) -> list:
        """Open milestones with their goals nested (id, title, done)."""
        def query(cols):
            q = self.sb.table("milestones").select(
                "id,startup_id,title,due_date,status,created_by_role,startups(name),goals(id,title,done,progress,est_progress)"
                + cols).eq("status", "open")
            if startup_id:
                q = q.eq("startup_id", startup_id)
            return q.order("due_date", desc=False, nullsfirst=False).limit(limit).execute().data or []

        def run():
            try:  # goal-less milestones carry their own progress (2026-10-milestone-progress.sql)
                return query(",progress,est_progress")
            except Exception:  # noqa: BLE001 - migration not run yet
                return query("")
        return self._guard("milestones", run, [])

    def update_milestone(self, milestone_id: str, patch: dict) -> bool:
        patch = {**patch, "updated_at": datetime.now(timezone.utc).isoformat()}
        return self._guard("update_milestone", lambda: bool(
            self.sb.table("milestones").update(patch).eq("id", milestone_id).execute()), False)

    def add_goal(self, milestone_id: str, title: str, created_by: str) -> bool:
        return self._guard("add_goal", lambda: bool(self.sb.table("goals").insert({
            "milestone_id": milestone_id, "title": title[:300], "created_by": created_by}).execute()), False)

    def update_goal(self, goal_id: str, patch: dict) -> bool:
        if "done" in patch:
            patch = {**patch, "done_at": datetime.now(timezone.utc).isoformat() if patch["done"] else None}
        return self._guard("update_goal", lambda: bool(
            self.sb.table("goals").update(patch).eq("id", goal_id).execute()), False)

    def sync_milestone(self, milestone_id: str, reopen: bool = True) -> str | None:
        """Keeps a milestone's status in step with its goals: all done -> done; a goal added or unticked -> open again
        (`reopen`; ticking a goal never reopens a milestone a mentor already marked done). Returns the new status when it changed."""
        def run():
            rows = self.sb.table("milestones").select("status,goals(done)").eq("id", milestone_id).execute().data
            if not rows or rows[0]["status"] not in ("open", "done"):
                return None  # dropped milestones stay dropped
            goals = rows[0].get("goals") or []
            want = "done" if goals and all(g.get("done") for g in goals) else "open"
            if want == rows[0]["status"] or (want == "open" and not reopen):
                return None
            self.sb.table("milestones").update({"status": want, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", milestone_id).execute()
            return want
        return self._guard("sync_milestone", run, None)

    def remove_goal(self, goal_id: str) -> bool:
        return self._guard("remove_goal", lambda: bool(
            self.sb.table("goals").delete().eq("id", goal_id).execute()), False)

    # --- meeting proposals awaiting confirmation ---
    def save_meeting(self, requested_by: str, payload: dict) -> str | None:
        def run():
            res = self.sb.table("pending_meetings").insert({"requested_by": requested_by, "payload": payload}).execute()
            return res.data[0]["id"] if res.data else None
        return self._guard("save_meeting", run, None)

    def get_meeting(self, meeting_id: str) -> dict | None:
        def run():
            rows = self.sb.table("pending_meetings").select("*").eq("id", meeting_id).execute().data
            return rows[0] if rows else None
        return self._guard("get_meeting", run, None)

    def set_meeting_payload(self, meeting_id: str, payload: dict) -> bool:
        return self._guard("set_meeting_payload", lambda: bool(
            self.sb.table("pending_meetings").update({"payload": payload}).eq("id", meeting_id).execute().data), False)

    def claim_meeting(self, meeting_id: str) -> bool:
        """Deletes the proposal and says whether this call was the one that removed it (stops a double click acting twice)."""
        failed = object()
        got = self._guard("claim_meeting", lambda: self.sb.table("pending_meetings").delete().eq("id", meeting_id).execute().data, failed)
        return True if got is failed else bool(got)  # a database hiccup must not leave the button doing nothing

    def delete_meeting(self, meeting_id: str):
        self._guard("delete_meeting", lambda: self.sb.table("pending_meetings").delete().eq("id", meeting_id).execute(), None)
