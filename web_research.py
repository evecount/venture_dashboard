"""
Web research for the assistant: Gemini with Google Search grounding returns a short factual brief plus its sources.
Used for outside facts (competitors, grants, events, market numbers, how-tos), never for program data.
HTTP is injectable so everything is testable offline.
"""

from transcribe import GEMINI_URL, _default_http

MAX_SOURCES = 5
PROMPT = (
    "Research this for a startup founder or mentor in a Singapore venture studio: {query}\n"
    "Answer as a tight factual brief of at most about 200 words: specific names, numbers, dates, prices and eligibility rules, "
    "Singapore context first when it matters. Say plainly when something could not be confirmed. No preamble."
)


def research(query: str, api_key: str, model: str, http=_default_http) -> str:
    """A brief with numbered sources, or an explanation of why there is none. Raises on transport errors."""
    body = {"contents": [{"parts": [{"text": PROMPT.format(query=query.strip()[:500])}]}],
            "tools": [{"google_search": {}}], "generationConfig": {"temperature": 0.2}}
    res = http("POST", GEMINI_URL.format(model=model), headers={"x-goog-api-key": api_key, "content-type": "application/json"},
               json=body).json()
    cand = (res.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in ((cand.get("content") or {}).get("parts") or [])).strip()
    sources, seen = [], set()
    for chunk in (cand.get("groundingMetadata") or {}).get("groundingChunks") or []:
        web = chunk.get("web") or {}
        if web.get("uri") and web["uri"] not in seen:
            seen.add(web["uri"])
            sources.append(f"{len(sources) + 1}. <{web['uri']}|{(web.get('title') or 'source').replace('|', '-')}>")
        if len(sources) >= MAX_SOURCES:
            break
    if not text:
        return "I couldn't find anything reliable on that."
    return text + ("\nSources:\n" + "\n".join(sources) if sources else "\n(No web sources came back, so treat this as unverified.)")
