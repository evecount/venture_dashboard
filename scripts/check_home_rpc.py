"""
After running supabase/migrations/2026-10-mentor-home-rpc.sql: compare the database function with the Python it replaces.

    python scripts/check_home_rpc.py

Prints OK, or every startup whose numbers differ. Read-only.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
from supabase import create_client  # noqa: E402

import integrations  # noqa: E402
from bot_memory import Memory  # noqa: E402

load_dotenv(ROOT / ".env")
sb = create_client(os.environ["VITE_SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
data = sb.rpc("mentor_home_data", {"p_days": 7}).execute().data
memory = Memory(sb)
bad = 0
for s in data["startups"]:
    sid = s["id"]
    want = integrations.activity_summary(sb, sid)
    got = {"commits": 0, "prs_opened": 0, "prs_merged": 0, "issues_closed": 0, "meetings": 0, "external_meetings": 0,
           "signals": 0, **(data["activity"].get(sid) or {})}
    for key in ("commits", "prs_opened", "prs_merged", "issues_closed", "meetings", "external_meetings", "signals"):
        if want[key] != got[key]:
            bad += 1
            print(f"{s['name']}: {key} python={want[key]} rpc={got[key]}")
    rows = integrations.github_connections(sb, sid)
    gh = data["github"].get(sid) or {"connected": False, "has_tracked": False}
    if bool(rows) != gh["connected"] or any(integrations.monitored_repos(r) for r in rows) != gh["has_tracked"]:
        bad += 1
        print(f"{s['name']}: github connected/tracked differs: python={bool(rows)}/{any(integrations.monitored_repos(r) for r in rows)} rpc={gh}")
    goals = [g for m in memory.milestones(sid) for g in (m.get("goals") or [])]
    tot = data["goals"].get(sid) or {"goals_total": 0, "goals_done": 0}
    if (len(goals), sum(1 for g in goals if g.get("done"))) != (tot["goals_total"], tot["goals_done"]):
        bad += 1
        print(f"{s['name']}: goals python={len(goals)}/{sum(1 for g in goals if g.get('done'))} rpc={tot}")
print("OK: the function matches the Python path for", len(data["startups"]), "startups" if not bad else f"MISMATCHES: {bad}")
