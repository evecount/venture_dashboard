"""Does the chat model actually act on typical requests? Sends a few real requests to the real model(s) with the bot's real tools
and checks that each one produced the right result (a meeting card, a task, a note...). Run it whenever the model changes:

    python scripts/model_check.py
    python scripts/model_check.py --runs 3

Nothing real is touched: the people, startups and database are in-memory stand-ins (the same ones the unit tests use), and nobody
is messaged. It only reads the AI settings from .env (GEMINI_API_KEY, AI_*). Exit code 1 if any check fails."""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tests")]

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
    load_dotenv(os.path.join(os.getcwd(), ".env"))  # run from the bot's folder (e.g. on the VM) to use its settings
except ImportError:
    pass
from openai import OpenAI  # noqa: E402

from bot_agent import Agent  # noqa: E402
from test_bot_agent import FakeMemory, FakeSB, MENTOR, STARTUPS  # noqa: E402

CASES = [
    ("a meeting", "Set a meeting tomorrow with everyone at 4.30pm virtual", lambda out, mem: bool(out["meetings"])),
    ("a task", "Add a task for Auvira: chase pricing by Friday", lambda out, mem: bool(mem.tasks)),
    ("a note", "Save a note on Auvira: they are blocked on legal review", lambda out, mem: bool(mem.notes)),
    ("an announcement", "Announce to everyone that I am away on Monday",
     lambda out, mem: bool(out["meetings"] or out.get("announcements") or out["announce_now"])),
    ("plain chat (no action)", "thanks, that's all", lambda out, mem: bool(out["text"]) and not out["meetings"] and not mem.tasks and not mem.notes),
]


def targets() -> list:
    gem_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("QWEN_API_KEY") or os.environ.get("OPENAI_API_KEY")
    found = []
    if gem_key:
        model = os.environ.get("AI_MODEL") or "gemini-3.8-flash"
        base = os.environ.get("AI_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta/openai/"
        found.append((f"Gemini ({model})", OpenAI(api_key=gem_key, base_url=base), model))
    return found


def run_case(client, model, text):
    mem = FakeMemory()
    ids = iter(f"proposal-{i}" for i in range(50))
    mem.save_meeting = lambda who, payload: next(ids)  # proposals are kept in memory only
    people = {"startups": STARTUPS,
              "founders": [{"name": "Ann", "email": "ann@example.com", "slack_user_id": "UANN00001", "startups": {"name": "Auvira"}}],
              "mentors": [{"name": "Mo", "email": "mo@example.com", "slack_user_id": "UM"}]}
    agent = Agent(client, model, FakeSB(people), mem, studio_connected=lambda: True)
    agent._context_parts = lambda ident: {"ctx": "CTX", "sched": "", "aware": "", "channels": ""}
    return agent.respond(MENTOR, text), mem


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1, help="times to try each request (models are not always consistent)")
    args = ap.parse_args()
    found = targets()
    if not found:
        print("No model configured: set GEMINI_API_KEY in .env")
        return 2
    failed = 0
    for label, client, model in found:
        print(f"\n== {label}")
        for name, text, check in CASES:
            passes = 0
            note = ""
            for _ in range(args.runs):
                try:
                    out, mem = run_case(client, model, text)
                    ok = bool(check(out, mem))
                    if not ok:
                        note = f"  said: {out['text'][:110]!r}"
                except Exception as e:  # noqa: BLE001
                    ok, note = False, f"  error: {type(e).__name__}: {str(e)[:110]}"
                passes += ok
            failed += passes < args.runs
            print(f"  {'PASS' if passes == args.runs else 'FAIL'}  {name}: {passes}/{args.runs}{note}")
    print("\nAll checks passed." if not failed else f"\n{failed} check(s) failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
