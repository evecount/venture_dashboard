"""
Side-by-side trial of Gemini's dedicated speech model against the transcript founders actually see.

After a voice note is transcribed the usual way, the same audio is sent to the candidate model in the background.
Both texts, both timings and a similarity score go to `voice_comparisons` (service role only, kept 14 days, no user ids).
Founders never see the candidate's text. The Developer Home tab shows the summary.
"""

import difflib
import threading
import time
from datetime import datetime, timedelta, timezone

KEEP_DAYS = 14
_memory: list = []  # fallback while the table doesn't exist (lost on restart)


def similarity(a: str, b: str) -> float:
    """0..1 word-level similarity, ignoring case and punctuation."""
    words = lambda t: "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in t or "").split()
    return round(difflib.SequenceMatcher(None, words(a), words(b)).ratio(), 3)


def word_diff(a: str, b: str, limit: int = 6) -> list:
    """['lah -> lor', ...]: the spans where the two transcripts disagree."""
    wa, wb = (a or "").split(), (b or "").split()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, wa, wb).get_opcodes():
        if op != "equal":
            out.append(f"{' '.join(wa[i1:i2]) or '∅'} → {' '.join(wb[j1:j2]) or '∅'}")
    return out[:limit]


def record(sb, row: dict):
    _memory.append(row)
    del _memory[:-200]
    try:
        sb.table("voice_comparisons").insert(row).execute()
    except Exception as e:  # noqa: BLE001 - table not created yet: keep it in memory
        print(f"[Voice Compare Warning] {e}")


def compare(sb, data: bytes, mime: str, current_text: str, current_ms: int, candidate, model: str):
    """Runs the candidate (a callable data, mime -> text) and records the result. Never raises."""
    t = time.monotonic()
    row = {"model": model, "current_text": current_text, "current_ms": current_ms,
           "created_at": datetime.now(timezone.utc).isoformat()}
    try:
        text = candidate(data, mime)
        row.update(candidate_text=text, candidate_ms=int((time.monotonic() - t) * 1000), similarity=similarity(current_text, text))
    except Exception as e:  # noqa: BLE001
        row.update(candidate_text=None, candidate_ms=int((time.monotonic() - t) * 1000), similarity=None, error=str(e)[:300])
    record(sb, row)
    return row


def compare_in_background(*args, **kwargs):
    threading.Thread(target=compare, args=args, kwargs=kwargs, daemon=True).start()


def recent(sb, days: int = 7) -> list:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        return sb.table("voice_comparisons").select("*").gte("created_at", since).order("created_at", desc=True).limit(200).execute().data or []
    except Exception:  # noqa: BLE001
        return [r for r in _memory if r["created_at"] >= since]


def report(rows: list) -> str:
    """Plain-text summary for the Developer view."""
    if not rows:
        return "No voice notes compared yet. Each new voice note is also sent to the candidate model in the background."
    nl = chr(10)
    ok = [r for r in rows if r.get("similarity") is not None]
    avg = lambda xs: sum(xs) / len(xs) if xs else 0
    lines = [f"Voice notes compared: {len(rows)} (last 7 days) · model {rows[0].get('model')}"]
    if ok:
        same = sum(1 for r in ok if r["similarity"] >= 0.999)
        lines += [f"Word match with today's transcript: {avg([r['similarity'] for r in ok]) * 100:.0f}% on average · identical {same}/{len(ok)}",
                  f"Speed: today's model {avg([r['current_ms'] for r in ok]) / 1000:.1f}s · candidate {avg([r['candidate_ms'] for r in ok]) / 1000:.1f}s"]
    failed = len(rows) - len(ok)
    if failed:
        lines.append(f"Candidate failed on {failed}: {next(r.get('error') for r in rows if r.get('similarity') is None)}")
    worst = sorted((r for r in ok if r["similarity"] < 0.999), key=lambda r: r["similarity"])[:5]
    if worst:
        lines += ["", "Biggest differences (today's → candidate):"]
        for r in worst:
            lines.append(f"• {r['similarity'] * 100:.0f}% match: " + " · ".join(word_diff(r["current_text"], r["candidate_text"])))
    return nl.join(lines)


def prune(sb):
    try:
        sb.table("voice_comparisons").delete().lt("created_at", (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).isoformat()).execute()
    except Exception:  # noqa: BLE001
        pass
