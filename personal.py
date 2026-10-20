"""
Per-person behaviour: standing instructions each person gives the bot in chat ("always use bullet points", "include
GitHub activity whenever I ask about a startup"), and requests for things it can't do yet, which go to the developers.

Instructions only shape how the bot talks to and works for that one person. They can't change roles, permissions,
privacy or code: tools are gated in code, and the prompt ranks the program's rules above them. Stored in the existing
`memories` table (subject_type 'behavior' / 'feature_request', subject_id = their Slack id), so no migration is needed;
these rows are filtered out wherever facts are shown.
"""

import json

BEHAVIOR, REQUEST = "behavior", "feature_request"
MAX_INSTRUCTIONS = 12
MAX_CHARS = 300
PRIVATE_KINDS = ("digest_prefs", BEHAVIOR, REQUEST)  # never shown as "remembered facts"


def instructions(sb, slack_id: str) -> list:
    try:
        rows = sb.table("memories").select("fact").eq("subject_type", BEHAVIOR).eq("subject_id", slack_id).limit(1).execute().data
        data = json.loads(rows[0]["fact"]) if rows else []
        return [str(x)[:MAX_CHARS] for x in data if str(x).strip()][:MAX_INSTRUCTIONS] if isinstance(data, list) else []
    except Exception as e:  # noqa: BLE001 - no instructions is a fine default
        print(f"[Personal Warning] {e}")
        return []


def _save(sb, slack_id: str, items: list) -> bool:
    try:
        sb.table("memories").delete().eq("subject_type", BEHAVIOR).eq("subject_id", slack_id).execute()
        if items:
            sb.table("memories").insert({"subject_type": BEHAVIOR, "subject_id": slack_id, "fact": json.dumps(items),
                                         "audience": "mentors", "created_by": slack_id}).execute()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[Personal Warning] save: {e}")
        return False


def add(sb, slack_id: str, instruction: str) -> tuple:
    """(ok, message). A near-duplicate replaces the older wording; the oldest drops off past the limit."""
    text = " ".join(str(instruction or "").split())[:MAX_CHARS]
    if not text:
        return False, "⚠️ What should I do differently?"
    items = [i for i in instructions(sb, slack_id) if i.lower() != text.lower()]
    items = (items + [text])[-MAX_INSTRUCTIONS:]
    return (True, f"⚙️ Got it. From now on, for you: _{text}_") if _save(sb, slack_id, items) else (False, "⚠️ I couldn't save that just now.")


def remove(sb, slack_id: str, which) -> tuple:
    """Removes by number (1-based, as listed), by matching words, or all of them ('all')."""
    items = instructions(sb, slack_id)
    if not items:
        return False, "You haven't given me any standing instructions yet."
    key = str(which or "").strip().lower()
    if key in ("all", "everything"):
        keep = []
    elif key.isdigit() and 1 <= int(key) <= len(items):
        keep = [i for n, i in enumerate(items, 1) if n != int(key)]
    else:
        keep = [i for i in items if key not in i.lower()] if key else items
    if len(keep) == len(items):
        return False, "⚠️ I couldn't tell which one. Your instructions are:\n" + numbered(items)
    return (True, "🗑 Removed. " + (("Still in place:\n" + numbered(keep)) if keep else "No standing instructions now.")) \
        if _save(sb, slack_id, keep) else (False, "⚠️ I couldn't save that just now.")


def numbered(items: list) -> str:
    return "\n".join(f"{n}. {i}" for n, i in enumerate(items, 1))


def save_request(sb, slack_id: str, name: str, text: str) -> bool:
    try:
        sb.table("memories").insert({"subject_type": REQUEST, "subject_id": slack_id, "fact": f"{name}: {text}"[:500],
                                     "audience": "mentors", "created_by": slack_id}).execute()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[Personal Warning] request: {e}")
        return False
