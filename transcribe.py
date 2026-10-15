"""
Voice notes: Slack audio -> transcript (Gemini), which then flows through the normal assistant like a typed update.

Speakers use English mixed with Singlish, so the prompt asks for a faithful transcript (no translating, no tidying).
HTTP is injectable so everything is testable offline.
"""

import base64

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
# Singlish particles help the dedicated speech model, which takes a vocabulary list instead of instructions.
SINGLISH_VOCAB = ["lah", "lor", "leh", "sia", "meh", "alamak", "shiok", "kopi", "can or not"]
MAX_BYTES = 18 * 1024 * 1024  # stays under Gemini's inline-data limit
MAX_FILES = 3

PROMPT = (
    "Transcribe this voice message word for word. The speaker uses English mixed with Singlish "
    "(words and particles such as lah, lor, leh, sia, can, alamak, shiok, kopi, etc.). Keep their words exactly as spoken: "
    "do not translate, formalise, summarise or correct grammar. Keep names, product names and numbers as heard. "
    "Add normal punctuation. Output ONLY the transcript text. If there is no intelligible speech, output exactly: [no speech]"
)

# Slack clips arrive under several names; Gemini wants a standard audio MIME type.
MIME_FIXES = {"audio/m4a": "audio/mp4", "audio/x-m4a": "audio/mp4", "video/mp4": "audio/mp4", "audio/mpeg": "audio/mp3",
              "audio/x-wav": "audio/wav", "audio/wave": "audio/wav", "video/webm": "audio/webm"}
EXT_MIMES = {"m4a": "audio/mp4", "mp4": "audio/mp4", "mp3": "audio/mp3", "wav": "audio/wav", "ogg": "audio/ogg",
             "webm": "audio/webm", "flac": "audio/flac", "aac": "audio/aac"}


def is_audio(f: dict) -> bool:
    mime = (f.get("mimetype") or "").lower()
    return (f.get("subtype") == "slack_audio" or mime.startswith("audio/")
            or (f.get("filetype") or "").lower() in EXT_MIMES and (f.get("filetype") or "").lower() != "mp4")


def gemini_mime(f: dict) -> str:
    mime = (f.get("mimetype") or "").lower()
    if mime in MIME_FIXES:
        return MIME_FIXES[mime]
    if mime.startswith("audio/"):
        return mime
    return EXT_MIMES.get((f.get("filetype") or "").lower(), "audio/mp4")


def _default_http(method: str, url: str, headers: dict | None = None, json: dict | None = None):
    import requests
    r = requests.request(method, url, headers=headers, json=json, timeout=90)
    r.raise_for_status()
    return r


def download(f: dict, token: str, http=_default_http) -> bytes:
    url = f.get("url_private_download") or f.get("url_private")
    if not url:
        raise ValueError("file has no download url")
    if f.get("size") and f["size"] > MAX_BYTES:
        raise ValueError("that audio file is too big")
    data = http("GET", url, headers={"Authorization": f"Bearer {token}"}).content
    if len(data) > MAX_BYTES:
        raise ValueError("that audio file is too big")
    return data


def transcribe_audio(data: bytes, mime: str, api_key: str, model: str, http=_default_http, hints: list | None = None) -> str:
    """Returns the transcript ('' when there is no speech). Retries once with a more generic MIME type for mp4 audio."""
    last = None
    prompt = PROMPT + (" Names and terms that may be spoken (spell them exactly like this if you hear them): "
                       + ", ".join(dict.fromkeys(h for h in (hints or []) if h)) + "." if hints else "")
    for m in (mime, "audio/aac") if mime == "audio/mp4" else (mime,):
        body = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": m, "data": base64.b64encode(data).decode()}}]}],
                "generationConfig": {"temperature": 0}}
        try:
            res = http("POST", GEMINI_URL.format(model=model), headers={"x-goog-api-key": api_key, "content-type": "application/json"},
                       json=body).json()
            parts = (((res.get("candidates") or [{}])[0].get("content") or {}).get("parts")) or []
            text = "".join(p.get("text", "") for p in parts).strip()
            return "" if text.lower().strip("[] .") == "no speech" else text
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"transcription failed: {last}")


def transcribe_dedicated(data: bytes, mime: str, api_key: str, model: str = "gemini-3.5-transcribe",
                         http=_default_http, vocab: list | None = None) -> str:
    """Gemini's speech-to-text model (Interactions API, inline audio, custom vocabulary). '' when nothing was heard."""
    mime = {"audio/mp4": "audio/m4a", "audio/aac": "audio/aac"}.get(mime, mime)  # its format list has m4a, not mp4
    terms = list(dict.fromkeys(t for t in (vocab or []) + SINGLISH_VOCAB if t))[:100]
    body = {"model": model,
            "input": [{"type": "audio", "data": base64.b64encode(data).decode(), "mime_type": mime}],
            "generation_config": {"transcription_config": {"custom_vocabulary": terms}}}
    res = http("POST", INTERACTIONS_URL, headers={"x-goog-api-key": api_key, "content-type": "application/json"}, json=body).json()
    texts = [c.get("text", "") for st in res.get("steps") or [] if st.get("type") == "model_output"
             for c in st.get("content") or [] if c.get("type") == "text"]
    return "".join(texts).strip()
