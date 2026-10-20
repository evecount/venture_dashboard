"""
Estimates goal progress from a founder's GitHub work and from their saved check-ins.

Every few minutes, for each startup with a monitored repository: take the commits, PRs and issues not assessed yet,
show them to the AI next to the startup's open goals, and ask which goals the work moves forward and to roughly
what percentage. Estimates are stored on the goal as "estimated" (never as official progress), only ever
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
    "partly (e.g. building the signup form advances 'Create landing page'). Commit messages, PR descriptions and the "
    "changed file paths are the evidence: paths show what was really built (src/pages/pricing.tsx is a pricing page, "
    "tests/ only is testing, README or config only is housekeeping). Progress is the TOTAL for the goal so "
    "far (not an increment) and must not be below its current value. Non-code goals (interviews, emails, pricing) "
    "usually get no credit from code. Reply with JSON only: "
    '{"updates": [{"goal": "<ref>", "progress": <0-95>, "reason": "<one short sentence citing the work>", '
    '"looks_done": <true if the work clearly finishes the goal>}]}. Return an empty list if nothing applies.'
)

CHECKIN_SYSTEM = (
    "You estimate how far a startup's goals have progressed, using only the founder's check-in shown (their own "
    "words about what they did). Be conservative: credit only what the check-in clearly reports as done, not plans "
    "or intentions. Non-code goals count here (e.g. 'emailed 3 of the 5 RCs' puts 'Contact 5 RCs' at about 60%). "
    "Progress is the TOTAL for the goal so far (not an increment) and must not be below its current value. Reply "
    "with JSON only: "
    '{"updates": [{"goal": "<ref>", "progress": <0-95>, "reason": "<one short sentence quoting what was done>", '
    '"looks_done": <true if the check-in says the goal is finished>}]}. Return an empty list if nothing applies.'
)
SOURCES = {"github": ("your GitHub work", SYSTEM, "NEW GITHUB WORK (oldest first):"),
           "checkin": ("your check-in", CHECKIN_SYSTEM, "FOUNDER CHECK-IN:")}


def goal_value(g: dict) -> tuple[int, bool]:
    """(percent, is_estimate) for display: done = 100; else the bot's estimate if any, else official progress."""
    if g.get("done"):
        return 100, False
    if g.get("est_progress") is not None:
        return int(g["est_progress"]), True
    return int(g.get("progress") or 0), False


def milestone_value(goals: list, milestone: dict | None = None) -> tuple[int, bool]:
    """Average of the goals. A milestone with no goals carries its own progress (and estimate) instead."""
    if not goals:
        if not milestone:
            return 0, False
        return goal_value({**milestone, "done": milestone.get("status") == "done"})
    vals = [goal_value(g) for g in goals]
    return round(sum(v for v, _ in vals) / len(vals)), any(e for _, e in vals)


def build_prompt(goals: list, work: list, heading: str = SOURCES["github"][2]) -> str:
    lines = ["OPEN GOALS (ref · milestone · goal · current %):"]
    for ref, g in goals:
        title = "(the milestone as a whole: it has no separate goals)" if g.get("kind") == "milestone" else g["title"]
        lines.append(f"- {ref} · {g['milestone']} · {title} · {goal_value(g)[0]}%")
    lines.append("")
    lines.append(heading)
    for s in work:
        if s.get("meta") is not None:  # a GitHub signal: commit messages, PR description and changed files
            lines.append(f"- {s['created_at'][:10]} · {integrations.describe_work(s, max_files=25)}")
        else:
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


def item_ref(g: dict) -> str:
    """Button value for a goal ("<id>") or a goal-less milestone ("m:<id>")."""
    return f"m:{g['id']}" if g.get("kind") == "milestone" else g["id"]


def table_for(g: dict) -> str:
    return "milestones" if g.get("kind") == "milestone" else "goals"


def card(change: dict) -> list:
    """Slack card for one estimate: confirm it, set your own number, or (if it looks finished) mark the goal done."""
    g = change["goal"]
    ref = item_ref(g)
    where = "" if g.get("kind") == "milestone" else f" ({g['milestone']})"
    source = SOURCES.get(change.get("source") or "github", SOURCES["github"])[0]
    text = (f"📈 *{g['title']}*{where} looks about *{change['new']}%* done from {source}"
            + (f": {change['reason']}" if change["reason"] else ".")
            + "\nIt shows as an estimate until you confirm it.")
    options = [{"text": {"type": "plain_text", "text": f"{p}%"}, "value": f"{ref}|{p}"} for p in range(10, 100, 10)]
    elements = [
        {"type": "button", "style": "primary", "text": {"type": "plain_text", "text": f"Confirm {change['new']}%"},
         "action_id": "confirm_goal_estimate", "value": ref},
        {"type": "static_select", "action_id": "set_goal_progress", "options": options,
         "placeholder": {"type": "plain_text", "text": "Set it myself"}},
    ]
    if change["looks_done"]:
        elements.append({"type": "button", "text": {"type": "plain_text", "text": "It's done"},
                         "action_id": "mark_goal_done", "value": ref})
    return [{"type": "section", "text": {"type": "mrkdwn", "text": text}}, {"type": "actions", "elements": elements}]


def _monitored_work(sb, startup_id: str, since: str) -> tuple:
    """(work from monitored repos, created_at of the last row read). The cursor lets a window made only of
    unmonitored repos' signals be skipped instead of being re-read forever."""
    rows = (sb.table("signals").select("id,type,headline,detail,meta,created_at").eq("startup_id", startup_id)
            .in_("type", list(WORK_TYPES)).gt("created_at", since).order("created_at").limit(80).execute().data) or []
    watched = integrations.monitored_for_startup(sb, startup_id)
    return [r for r in rows if (r.get("meta") or {}).get("repo") in watched], (rows[-1]["created_at"] if rows else None)


def _open_milestones(sb, startup_id: str) -> list:
    q = lambda cols: (sb.table("milestones").select(cols).eq("startup_id", startup_id).eq("status", "open")
                      .execute().data) or []
    try:
        return q("id,title,progress,est_progress,goals(id,title,done,progress,est_progress)")
    except Exception:  # noqa: BLE001 - milestone progress migration not run yet: goals only
        return q("id,title,goals(id,title,done,progress,est_progress)")


def _rateable(milestones: list) -> list:
    """Open goals, plus each goal-less milestone rated as a whole (needs the milestone progress columns)."""
    goals = [{**g, "milestone": m["title"]} for m in milestones for g in (m.get("goals") or []) if not g.get("done")]
    goals += [{"id": m["id"], "title": m["title"], "milestone": m["title"], "kind": "milestone", "done": False,
               "progress": m.get("progress"), "est_progress": m.get("est_progress")}
              for m in milestones if not m.get("goals") and "est_progress" in m]
    return goals


def _assess(sb, ai, model: str, startup_id: str, goals: list, work: list, source: str, notify, now: datetime) -> int:
    """Ask the AI, store the estimates that pass `decide`, and card the founders on a big move. Returns the count."""
    _, system, heading = SOURCES[source]
    refs = [(f"g{i + 1}", g) for i, g in enumerate(goals)]
    reply = ai.chat.completions.create(
        model=model, temperature=0.2,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": build_prompt(refs, work, heading)}],
    ).choices[0].message.content
    changes = decide(dict(refs), parse_reply(reply))
    for c in changes:
        c["source"] = source
        sb.table(table_for(c["goal"])).update({"est_progress": c["new"], "est_reason": c["reason"] or None,
                                               "est_at": now.isoformat()}).eq("id", c["goal"]["id"]).execute()
        if notify and (c["new"] - c["old"] >= NOTIFY_JUMP or c["looks_done"]):
            notify(startup_id, card(c), f"Progress estimate: {c['goal']['title']} ~{c['new']}%")
    return len(changes)


def from_checkin(sb, ai, model: str, startup_id: str, digest: str, notify=None, now: datetime | None = None) -> int:
    """After a founder saves a check-in: credit the goals it clearly reports progress on (code or not)."""
    if not (sb and ai and startup_id and (digest or "").strip()):
        return 0
    now = now or datetime.now(timezone.utc)
    try:
        goals = _rateable(_open_milestones(sb, startup_id))
        if not goals:
            return 0
        work = [{"created_at": now.isoformat(), "headline": "Check-in", "detail": digest.strip()[:1500]}]
        return _assess(sb, ai, model, startup_id, goals, work, "checkin", notify, now)
    except Exception as e:  # noqa: BLE001 - an estimate must never break saving a check-in
        print(f"[Progress Estimate Warning] check-in {startup_id}: {e}")
        return 0


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
            work, cursor = _monitored_work(sb, startup_id, since)
            if not work:
                if cursor:
                    sb.table("progress_estimate_state").upsert({
                        "startup_id": startup_id, "last_signal_at": cursor, "updated_at": now.isoformat()}).execute()
                continue
            goals = _rateable(_open_milestones(sb, startup_id))
            if not goals:
                continue  # leave the work unassessed: goals set later still get credit for it
            stored += _assess(sb, ai, model, startup_id, goals, work, "github", notify, now)
            sb.table("progress_estimate_state").upsert({
                "startup_id": startup_id, "last_signal_at": work[-1]["created_at"], "updated_at": now.isoformat()}).execute()
        except Exception as e:  # noqa: BLE001 - one startup's failure must not stop the others
            print(f"[Progress Estimate Warning] {startup_id}: {e}")
    return stored
