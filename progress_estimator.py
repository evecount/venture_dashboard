"""
Estimates goal progress from a founder's GitHub work.

Every few minutes, for each startup with a monitored repository: take the commits, PRs and issues not assessed yet,
show them to the AI next to the startup's open goals, and ask which goals the work moves forward and to roughly
what percentage. Estimates are stored on the goal as "estimated from GitHub" (never as official progress), only ever
go up, stop at 95%, and never mark a goal done. When an estimate moves a lot (or the work looks finished), the
founders get a Slack card to confirm it, set their own number, or mark the goal done.
"""

import json
import re
from datetime import datetime, timedelta, timezone

import integrations

WORK_TYPES = ("commit", "pull_request", "issue")
MAX_ESTIMATE = 95       # only a person marks a goal done
NOTIFY_JUMP = 10        # points of change worth a Slack card
FIRST_LOOKBACK_DAYS = 7  # on a startup's first run, assess the last week of work

SYSTEM = (
    "You estimate how far a startup's goals have progressed, using only the GitHub work shown. Be conservative: "
    "small or unrelated commits move nothing; give credit only where the work plausibly advances a goal, even "
    "partly (e.g. building the signup form advances 'Create landing page'). Progress is the TOTAL for the goal so "
    "far (not an increment) and must not be below its current value. Non-code goals (interviews, emails, pricing) "
    "usually get no credit from code. Reply with JSON only: "
    '{"updates": [{"goal": "<ref>", "progress": <0-95>, "reason": "<one short sentence citing the work>", '
    '"looks_done": <true if the work clearly finishes the goal>}]}. Return an empty list if nothing applies.'
)


def goal_value(g: dict) -> tuple[int, bool]:
    """(percent, is_estimate) for display: done = 100; else the bot's estimate if any, else official progress."""
    if g.get("done"):
        return 100, False
    if g.get("est_progress") is not None:
        return int(g["est_progress"]), True
    return int(g.get("progress") or 0), False


def milestone_value(goals: list) -> tuple[int, bool]:
    if not goals:
        return 0, False
    vals = [goal_value(g) for g in goals]
    return round(sum(v for v, _ in vals) / len(vals)), any(e for _, e in vals)


def build_prompt(goals: list, work: list) -> str:
    lines = ["OPEN GOALS (ref · milestone · goal · current %):"]
    for ref, g in goals:
        lines.append(f"- {ref} · {g['milestone']} · {g['title']} · {goal_value(g)[0]}%")
    lines.append("")
    lines.append("NEW GITHUB WORK (oldest first):")
    for s in work:
        detail = f" — {s['detail']}" if s.get("detail") else ""
        lines.append(f"- {s['created_at'][:10]} · {s['headline']}{detail}")
    return "\n".join(lines)


def parse_reply(text: str) -> list:
    """The AI's JSON (tolerating code fences or stray prose around it) -> list of update dicts."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    ups = data.get("updates") if isinstance(data, dict) else None
    return [u for u in (ups or []) if isinstance(u, dict)]


def decide(goals_by_ref: dict, updates: list) -> list:
    """
    Which estimates to store. Rules: known goal, not done, a whole number, capped at 95, and higher than both the
    current estimate and official progress (estimates only go up). Returns [{goal, new, old, reason, looks_done}].
    """
    out = []
    for u in updates:
        g = goals_by_ref.get(str(u.get("goal", "")).strip())
        if not g or g.get("done"):
            continue
        try:
            new = max(0, min(MAX_ESTIMATE, int(round(float(u.get("progress"))))))
        except (TypeError, ValueError):
            continue
        old = max(int(g.get("est_progress") or 0), int(g.get("progress") or 0))
        if new <= old:
            continue
        out.append({"goal": g, "new": new, "old": old, "reason": str(u.get("reason") or "")[:240],
                    "looks_done": bool(u.get("looks_done"))})
    return out


def card(change: dict) -> list:
    """Slack card for one estimate: confirm it, set your own number, or (if it looks finished) mark the goal done."""
    g = change["goal"]
    text = (f"📈 *{g['title']}* ({g['milestone']}) looks about *{change['new']}%* done from your GitHub work"
            + (f": {change['reason']}" if change["reason"] else ".")
            + "\nIt shows as an estimate until you confirm it.")
    options = [{"text": {"type": "plain_text", "text": f"{p}%"}, "value": f"{g['id']}|{p}"} for p in range(10, 100, 10)]
    elements = [
        {"type": "button", "style": "primary", "text": {"type": "plain_text", "text": f"Confirm {change['new']}%"},
         "action_id": "confirm_goal_estimate", "value": g["id"]},
        {"type": "static_select", "action_id": "set_goal_progress", "options": options,
         "placeholder": {"type": "plain_text", "text": "Set it myself"}},
    ]
    if change["looks_done"]:
        elements.append({"type": "button", "text": {"type": "plain_text", "text": "It's done"},
                         "action_id": "mark_goal_done", "value": g["id"]})
    return [{"type": "section", "text": {"type": "mrkdwn", "text": text}}, {"type": "actions", "elements": elements}]


def _monitored_work(sb, startup_id: str, since: str) -> list:
    rows = (sb.table("signals").select("id,type,headline,detail,meta,created_at").eq("startup_id", startup_id)
            .in_("type", list(WORK_TYPES)).gt("created_at", since).order("created_at").limit(80).execute().data) or []
    watched = integrations.monitored_for_startup(sb, startup_id)
    return [r for r in rows if (r.get("meta") or {}).get("repo") in watched]


def run(sb, ai, model: str, notify=None, now: datetime | None = None) -> int:
    """One pass over every startup with GitHub connected. `notify(startup_id, blocks, text)` sends Slack cards."""
    if not (sb and ai):
        return 0
    now = now or datetime.now(timezone.utc)
    try:
        conns = sb.table("integrations").select("startup_id").eq("provider", "github").execute().data or []
        state = {r["startup_id"]: r["last_signal_at"] for r in
                 (sb.table("progress_estimate_state").select("startup_id,last_signal_at").execute().data or [])}
    except Exception as e:  # noqa: BLE001 - migration not run yet
        print(f"[Progress Estimate Warning] {e}")
        return 0
    stored = 0
    for startup_id in sorted({c["startup_id"] for c in conns if c.get("startup_id")}):
        try:
            since = state.get(startup_id) or (now - timedelta(days=FIRST_LOOKBACK_DAYS)).isoformat()
            work = _monitored_work(sb, startup_id, since)
            if not work:
                continue
            milestones = (sb.table("milestones").select("title,goals(id,title,done,progress,est_progress)")
                          .eq("startup_id", startup_id).eq("status", "open").execute().data) or []
            goals = [{**g, "milestone": m["title"]} for m in milestones for g in (m.get("goals") or []) if not g.get("done")]
            if not goals:
                continue  # leave the work unassessed: goals set later still get credit for it
            changes = []
            if goals:
                refs = [(f"g{i + 1}", g) for i, g in enumerate(goals)]
                reply = ai.chat.completions.create(
                    model=model, temperature=0.2,
                    messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": build_prompt(refs, work)}],
                ).choices[0].message.content
                changes = decide(dict(refs), parse_reply(reply))
            for c in changes:
                sb.table("goals").update({"est_progress": c["new"], "est_reason": c["reason"] or None,
                                          "est_at": now.isoformat()}).eq("id", c["goal"]["id"]).execute()
                stored += 1
                if notify and (c["new"] - c["old"] >= NOTIFY_JUMP or c["looks_done"]):
                    notify(startup_id, card(c), f"Progress estimate: {c['goal']['title']} ~{c['new']}%")
            sb.table("progress_estimate_state").upsert({
                "startup_id": startup_id, "last_signal_at": work[-1]["created_at"], "updated_at": now.isoformat()}).execute()
        except Exception as e:  # noqa: BLE001 - one startup's failure must not stop the others
            print(f"[Progress Estimate Warning] {startup_id}: {e}")
    return stored
