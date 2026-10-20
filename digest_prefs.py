"""
What each person wants in their Monday briefing's news section: topics to cover and topics to skip.

Stored as one row per person in the existing `memories` table (subject_type 'digest_prefs', subject_id = their Slack
id), so no migration is needed. These rows are filtered out wherever facts are shown: a preference isn't a fact.
"""

import json

KIND = "digest_prefs"
MAX_TOPICS = 8
EMPTY = {"topics": [], "avoid": []}


def _clean(items) -> list:
    out = []
    for t in items or []:
        t = " ".join(str(t).split())[:80]
        if t and t.lower() not in {x.lower() for x in out}:
            out.append(t)
    return out[:MAX_TOPICS]


def get(sb, slack_id: str) -> dict:
    try:
        rows = sb.table("memories").select("fact").eq("subject_type", KIND).eq("subject_id", slack_id).limit(1).execute().data
        data = json.loads(rows[0]["fact"]) if rows else {}
        return {"topics": _clean(data.get("topics")), "avoid": _clean(data.get("avoid"))}
    except Exception as e:  # noqa: BLE001 - no preferences is a fine default
        print(f"[Digest Prefs Warning] {e}")
        return dict(EMPTY)


def update(sb, slack_id: str, topics=None, avoid=None, replace: bool = False) -> dict | None:
    """Adds (or, with replace, sets) topics and topics to avoid. A topic newly wanted stops being avoided, and the
    other way round. Returns the new preferences, or None when they couldn't be saved."""
    cur = dict(EMPTY) if replace else get(sb, slack_id)
    want, skip = _clean(topics), _clean(avoid)
    low = lambda xs: {x.lower() for x in xs}  # noqa: E731
    new = {"topics": _clean([t for t in cur["topics"] if t.lower() not in low(skip)] + want),
           "avoid": _clean([t for t in cur["avoid"] if t.lower() not in low(want)] + skip)}
    try:
        sb.table("memories").delete().eq("subject_type", KIND).eq("subject_id", slack_id).execute()
        sb.table("memories").insert({"subject_type": KIND, "subject_id": slack_id, "fact": json.dumps(new),
                                     "audience": "mentors", "created_by": slack_id}).execute()
        return new
    except Exception as e:  # noqa: BLE001
        print(f"[Digest Prefs Warning] save: {e}")
        return None


def describe(p: dict) -> str:
    parts = []
    if p.get("topics"):
        parts.append("more on " + ", ".join(p["topics"]))
    if p.get("avoid"):
        parts.append("less on " + ", ".join(p["avoid"]))
    return "; ".join(parts) or "no preferences yet (a mix of what's relevant to you)"
