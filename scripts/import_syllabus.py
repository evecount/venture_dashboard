"""
Import a participant's custom syllabus as milestones on the dashboard.

    python scripts/import_syllabus.py syllabi/<name>.json            # preview only
    python scripts/import_syllabus.py syllabi/<name>.json --apply    # write to Supabase

Each week becomes one mentor-issued milestone due on the week's last day; the week's deliverables (split on ';')
become its goals. Safe to re-run: weeks already imported (same startup and title) are skipped.
File shape: {"startup_id", "issued_by" (a mentor's Slack id), "weeks": [{"week", "sprint", "title", "end" (YYYY-MM-DD), "milestone"}]}
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def plan(spec: dict) -> list:
    """[(title, due_date, [goals])] for every week in the syllabus."""
    out = []
    for w in spec["weeks"]:
        goals = [g.strip(" .") for g in w["milestone"].split(";") if g.strip(" .")]
        out.append((f"Week {w['week']} (Sprint {w['sprint']}): {w['title']}", w["end"], goals))
    return out


def main(argv: list) -> int:
    path = Path(argv[1])
    spec = json.loads(path.read_text(encoding="utf-8"))
    rows = plan(spec)
    for title, due, goals in rows:
        print(f"{due}  {title}")
        for g in goals:
            print(f"            - {g}")
    if "--apply" not in argv:
        print(f"\n{len(rows)} milestones for {spec['startup_id']}. Preview only; add --apply to write them.")
        return 0
    from dotenv import load_dotenv
    from supabase import create_client
    load_dotenv(ROOT / ".env")
    sb = create_client(os.environ["VITE_SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    have = {r["title"] for r in sb.table("milestones").select("title").eq("startup_id", spec["startup_id"]).execute().data or []}
    added = 0
    for title, due, goals in rows:
        if title in have:
            continue
        ms = sb.table("milestones").insert({"startup_id": spec["startup_id"], "title": title, "due_date": due, "status": "open",
                                            "created_by": spec["issued_by"], "created_by_role": "mentor"}).execute().data[0]
        sb.table("goals").insert([{"milestone_id": ms["id"], "title": g, "created_by": spec["issued_by"]} for g in goals]).execute()
        added += 1
    print(f"\nAdded {added} milestones, skipped {len(rows) - added} already there.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
