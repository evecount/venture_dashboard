"""
Skills (skills/*.md): packaged instructions the agent loads only when a conversation needs them, plus the tools that need them.

Each skill is a markdown file in skills/ with a small header:

    ---
    name: meetings
    description: one line, shown in the skill list the model always sees
    roles: mentor, founder
    tools: schedule_meeting, change_meeting          (unlocked while the skill is loaded)
    triggers: \\b(meet|meeting)\\b                    (regex; pre-loads the skill when recent messages match)
    effort: low                                      (optional: think harder while it is loaded; none/low/medium/high)
    ---
    Instructions...

A skill only adds instructions and unlocks tools the role already has in code. It never grants a permission:
roles still gate every tool and arguments are still re-validated server-side.
"""

import os
import re

SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")
_FIELDS = ("name", "description", "roles", "tools", "triggers", "effort")
EFFORTS = ("none", "low", "medium", "high")  # how hard the model thinks; a skill can ask for more than the chat default


def parse(text: str) -> dict | None:
    """One skill file -> {name, description, roles, tools, trigger, body}, or None when the header is malformed."""
    m = re.match(r"\s*---\s*\n(.*?)\n---\s*\n(.*)", text, re.S)
    if not m:
        return None
    head = {}
    for line in m.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() in _FIELDS:
            head[key.strip()] = value.strip()
    if not head.get("name") or not head.get("description"):
        return None
    split = lambda v: [x.strip() for x in (v or "").split(",") if x.strip()]  # noqa: E731
    try:
        trigger = re.compile(head["triggers"], re.I) if head.get("triggers") else None
    except re.error:
        trigger = None
    return {"name": head["name"], "description": head["description"], "roles": split(head.get("roles")) or ["mentor", "founder"],
            "tools": split(head.get("tools")), "trigger": trigger, "body": m.group(2).strip(),
            "effort": head.get("effort") if head.get("effort") in EFFORTS else None}


def load(directory: str = SKILLS_DIR) -> dict:
    """{name: skill} for every valid skill file. A missing folder or a bad file is skipped, never fatal."""
    out = {}
    try:
        names = sorted(f for f in os.listdir(directory) if f.endswith(".md"))
    except OSError:
        return out
    for f in names:
        try:
            with open(os.path.join(directory, f), encoding="utf-8") as fh:
                skill = parse(fh.read())
        except OSError:
            skill = None
        if skill:
            out[skill["name"]] = skill
        else:
            print(f"[Skills Warning] skipped {f}: needs a --- header with name and description")
    return out


class Skills:
    def __init__(self, skills: dict | None = None):
        self.all = load() if skills is None else skills

    def for_role(self, role: str) -> dict:
        return {n: s for n, s in self.all.items() if role in s["roles"]}

    def index(self, role: str) -> str:
        """The always-on list: name and one line each."""
        mine = self.for_role(role)
        return "\n".join(f"- {n}: {s['description']}" for n, s in mine.items())

    def matching(self, role: str, text: str) -> list:
        """Skills whose trigger matches the recent conversation, so common requests need no extra round."""
        return [n for n, s in self.for_role(role).items() if s["trigger"] and s["trigger"].search(text or "")]

    def tools_of(self, names) -> set:
        return {t for n in names for t in (self.all.get(n) or {}).get("tools", [])}

    def gated(self) -> set:
        """Every tool some skill unlocks."""
        return self.tools_of(self.all)

    def effort(self, names, base: str) -> str:
        """The highest thinking level asked for by the chat default or any loaded skill."""
        wanted = [base] + [(self.all.get(n) or {}).get("effort") for n in names]
        ranked = [e for e in wanted if e in EFFORTS]
        return max(ranked, key=EFFORTS.index) if ranked else base

    def instructions(self, names, role: str) -> str:
        mine = self.for_role(role)
        return "\n\n".join(f"### Skill: {n}\n{mine[n]['body']}" for n in names if n in mine)
