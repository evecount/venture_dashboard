"""
Syllabus upload: a mentor attaches a participant's custom syllabus (PDF or text) and the bot turns it into dashboard milestones.

Gemini reads the document into weeks; everything after that is plain code so it can be tested offline:
- one milestone per week, due on the week's last day, the week's deliverables as its goals;
- milestones the startup already has are never changed or removed: syllabus items that match an existing
  milestone or goal are left out (the existing one wins), and a week with nothing new is skipped;
- "replace" removes only milestones an earlier import made (titles start "Week N (Sprint N):"), never one a person set.
HTTP is injectable like transcribe.py.
"""

import base64
import json
import re
from datetime import date, timedelta

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_BYTES = 12 * 1024 * 1024
MAX_WEEKS = 60
MAX_GOALS = 8
IMPORTED_RE = re.compile(r"^Week \d+( \(Sprint \d+\))?: ")
REPLACE_RE = re.compile(r"\b(replace|redo|re-?import|overwrite|start over|swap)\b", re.IGNORECASE)
STOP = {"the", "a", "an", "and", "of", "to", "for", "in", "on", "with", "by", "or", "is", "are", "be", "at", "from", "as",
        "week", "sprint", "v1", "first", "initial"}

PROMPT = (
    "This document is a custom program syllabus for one participant of a venture studio. Extract it as JSON with exactly this shape: "
    '{"participant": "full name", "company": "company name", "venture": "product or venture name", '
    '"weeks": [{"week": 1, "sprint": 1, "title": "short title in sentence case (keep acronyms like GTM or ICP uppercase), without the word Week", "start": "YYYY-MM-DD", "end": "YYYY-MM-DD", '
    '"notes": "schedule accommodations for that week such as courses or travel, else empty", '
    '"milestones": ["each deliverable as its own short string"]}]}. '
    "One entry per week, in order. The weeks list the dates without a year: work out the year from the program start and end dates. "
    "Split the week's Milestone line into its separate deliverables (one string each, keep their wording). "
    "Do not invent weeks or deliverables. Output only the JSON."
)


def is_document(f: dict) -> bool:
    mime = (f.get("mimetype") or "").lower()
    kind = (f.get("filetype") or "").lower()
    return mime in ("application/pdf", "text/plain", "text/markdown") or kind in ("pdf", "text", "markdown", "txt", "md")


def looks_like_syllabus(f: dict, text: str) -> bool:
    return is_document(f) and bool(re.search(r"syllab|curriculum", f"{f.get('name', '')} {text}", re.IGNORECASE))


def wants_replace(text: str) -> bool:
    return bool(REPLACE_RE.search(text or ""))


def _doc_mime(f: dict) -> str:
    mime = (f.get("mimetype") or "").lower()
    if mime == "application/pdf" or (f.get("filetype") or "").lower() == "pdf":
        return "application/pdf"
    return "text/plain"


def extract(data: bytes, f: dict, api_key: str, model: str, today: date, http) -> dict:
    """Reads the document with Gemini and returns cleaned weeks. Raises ValueError when it isn't a syllabus."""
    body = {"contents": [{"parts": [{"text": PROMPT + f" Today is {today.isoformat()}."},
                                    {"inline_data": {"mime_type": _doc_mime(f), "data": base64.b64encode(data).decode()}}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
    res = http("POST", GEMINI_URL.format(model=model), headers={"x-goog-api-key": api_key, "content-type": "application/json"}, json=body).json()
    parts = (((res.get("candidates") or [{}])[0].get("content") or {}).get("parts")) or []
    raw = "".join(p.get("text", "") for p in parts).strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        return clean(json.loads(raw))
    except json.JSONDecodeError as e:
        raise ValueError("I couldn't read that file as a week-by-week syllabus") from e


def _day(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def week_title(w: dict) -> str:
    sprint = f" (Sprint {w['sprint']})" if w.get("sprint") else ""
    notes = f" ({w['notes']})" if w.get("notes") else ""
    return f"Week {w['week']}{sprint}: {w['title']}{notes}"[:200]


def clean(spec: dict) -> dict:
    """Validated syllabus: weeks with real dates, sorted, trimmed, capped. Raises ValueError when there is nothing usable."""
    weeks = []
    for i, w in enumerate((spec or {}).get("weeks") or [], 1):
        if not isinstance(w, dict):
            continue
        end = _day(w.get("end"))
        start = _day(w.get("start")) or (end - timedelta(days=6) if end else None)
        items = [str(x).strip(" .;")[:200] for x in (w.get("milestones") or []) if str(x).strip(" .;")][:MAX_GOALS]
        title = str(w.get("title") or "").strip()[:120]
        if not (end and title):
            continue
        notes = str(w.get("notes") or "").strip()
        weeks.append({"week": int(w.get("week") or i), "sprint": int(w["sprint"]) if str(w.get("sprint") or "").isdigit() else None,
                      "title": title, "start": start.isoformat(), "end": end.isoformat(),
                      "notes": notes[:90], "milestones": items})
        if len(weeks) >= MAX_WEEKS:
            break
    if not weeks:
        raise ValueError("I couldn't find any weeks with dates in that file")
    weeks.sort(key=lambda w: w["end"])
    return {"participant": str(spec.get("participant") or "").strip()[:100], "company": str(spec.get("company") or "").strip()[:100],
            "venture": str(spec.get("venture") or "").strip()[:100], "weeks": weeks}


# ---------- which startup ----------

def _tokens(s: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 1}


def match_startups(spec: dict, text: str, founders: list, startups: list) -> list:
    """
    Startup ids this syllabus is probably for, best evidence first: the participant's name against founders, then the
    company/venture against startup names, then names mentioned in the mentor's message. One id = confident.
    """
    who = _tokens(spec.get("participant"))
    tier1 = {f["startup_id"] for f in founders if f.get("startup_id") and who and (_tokens(f["name"]) <= who or who <= _tokens(f["name"]))}
    if tier1:
        return sorted(tier1)
    blob = " ".join([spec.get("company") or "", spec.get("venture") or ""]).lower()
    tier2 = {s["id"] for s in startups if len(s["name"]) > 2 and s["name"].lower() in blob}
    if tier2:
        return sorted(tier2)
    said = (text or "").lower()
    tier3 = {s["id"] for s in startups if len(s["name"]) > 2 and s["name"].lower() in said}
    tier3 |= {f["startup_id"] for f in founders if f.get("startup_id") and len(f["name"].split()[0]) > 2
              and re.search(r"\b" + re.escape(f["name"].split()[0].lower()) + r"\b", said)}
    return sorted(tier3)


# ---------- not overlapping what exists ----------

def similar(a: str, b: str) -> bool:
    """Same work, worded differently: most of the shorter text's meaningful words appear in the other."""
    x, y = _tokens(a) - STOP, _tokens(b) - STOP
    if len(x) < 2 or len(y) < 2:
        return a.strip().lower() == b.strip().lower()
    shared = len(x & y)
    return shared >= 2 and shared / min(len(x), len(y)) >= 0.7


def plan_import(weeks: list, existing: list) -> dict:
    """
    existing: the startup's milestones, each {title, status, goals: [{title}]}.
    Returns {"add": [{title, due, goals}], "covered": [{item, by}], "skipped_weeks": [titles], "have": [titles already imported]}.
    A syllabus deliverable that matches an existing milestone title or goal is left out and the existing one is used.
    """
    live = [m for m in existing if m.get("status") != "dropped"]
    texts = [(m["title"], m["title"]) for m in live] + [(g["title"], m["title"]) for m in live for g in (m.get("goals") or [])]
    have = {m["title"] for m in live}
    out = {"add": [], "covered": [], "skipped_weeks": [], "have": []}
    for w in weeks:
        title = week_title(w)
        if title in have:
            out["have"].append(title)
            continue
        goals = []
        for item in w["milestones"] or [w["title"]]:
            hit = next((owner for text, owner in texts if similar(item, text)), None)
            if hit:
                out["covered"].append({"item": item, "by": hit})
            else:
                goals.append(item)
        if goals:
            out["add"].append({"title": title, "due": w["end"], "goals": goals})
        else:
            out["skipped_weeks"].append(title)
    return out


def removable(existing: list) -> list:
    """Milestones an earlier import made that can be safely replaced: still open, no finished goal."""
    return [m for m in existing if IMPORTED_RE.match(m["title"]) and m.get("status") == "open"
            and not any(g.get("done") for g in (m.get("goals") or []))]


def load_existing(sb, startup_id: str) -> list:
    return (sb.table("milestones").select("id,title,status,due_date,goals(title,done)").eq("startup_id", startup_id).execute().data) or []


def apply_import(sb, startup_id: str, by: str, add: list, remove_ids: list) -> int:
    """Writes the planned milestones (and removes the replaceable ones first). Returns how many were added."""
    for mid in remove_ids:
        sb.table("milestones").delete().eq("id", mid).execute()
    added = 0
    for m in add:
        row = sb.table("milestones").insert({"startup_id": startup_id, "title": m["title"], "due_date": m["due"], "status": "open",
                                             "created_by": by, "created_by_role": "mentor"}).execute().data[0]
        if m["goals"]:
            sb.table("goals").insert([{"milestone_id": row["id"], "title": g, "created_by": by} for g in m["goals"]]).execute()
        added += 1
    return added


def supersede(sb, startup_id: str, keep_id: str, texts: list) -> list:
    """
    A milestone or goal someone just added wins over the syllabus: syllabus goals that match any of `texts` are removed
    (and a syllabus week left with no goals goes with them). Finished goals and anything not made by an import stay.
    Returns what was removed, for the reply.
    """
    removed = []
    texts = [t for t in texts if t]
    if not texts:
        return removed
    for m in removable(load_existing(sb, startup_id)):
        if m["id"] == keep_id:
            continue
        goals = m.get("goals") or []
        if not goals:  # a week imported with no deliverables: its title is the item
            if any(similar(IMPORTED_RE.sub("", m["title"]), t) for t in texts):
                sb.table("milestones").delete().eq("id", m["id"]).execute()
                removed.append(m["title"])
            continue
        hit = [g for g in goals if any(similar(g["title"], t) for t in texts)]
        for g in hit:
            sb.table("goals").delete().eq("milestone_id", m["id"]).eq("title", g["title"]).execute()
            removed.append(g["title"])
        if hit and len(hit) == len(goals):
            sb.table("milestones").delete().eq("id", m["id"]).execute()
    return removed
