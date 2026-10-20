"""
Search by meaning: "payments" finds "Stripe checkout keeps failing". Gemini embeddings, ranked in memory.

The caller hands over the records the asker may see (already privacy-filtered); this module only ranks them.
Vectors are cached by the text's hash in a small JSON file, so each record is embedded once; a cohort's few thousand
records rank in milliseconds without a vector database. HTTP is injectable so everything is testable offline.
"""

import hashlib
import json
import math
import os
import threading

from transcribe import _default_http

EMBED_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"
MODEL = "gemini-embedding-001"
DIMS = 256
BATCH = 100
MIN_SCORE = 0.5  # below this a match is noise
CACHE_PATH = os.environ.get("SEMANTIC_CACHE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".semantic_cache.json")


def _key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:20]


def _unit(v: list) -> list:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class Semantic:
    def __init__(self, api_key: str, model: str = MODEL, http=_default_http, cache_path: str | None = CACHE_PATH):
        self.api_key, self.model, self.http, self.path = api_key, model, http, cache_path
        self.lock = threading.Lock()
        self.vectors = self._load()

    def _load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError, TypeError):
            return {}

    def _save(self):
        if not self.path:
            return
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.vectors, f)
            os.replace(tmp, self.path)
        except OSError as e:
            print(f"[Semantic Warning] cache not saved: {e}")

    def _embed(self, texts: list, task: str) -> list:
        out = []
        for i in range(0, len(texts), BATCH):
            chunk = texts[i:i + BATCH]
            body = {"requests": [{"model": f"models/{self.model}", "content": {"parts": [{"text": t[:2000]}]},
                                  "taskType": task, "outputDimensionality": DIMS} for t in chunk]}
            res = self.http("POST", EMBED_URL.format(model=self.model), headers={"x-goog-api-key": self.api_key,
                                                                               "content-type": "application/json"}, json=body).json()
            out += [_unit(e["values"]) for e in res["embeddings"]]
        return out

    def rank(self, query: str, docs: list, text_of=lambda d: d["text"], limit: int = 25, min_score: float = MIN_SCORE) -> list:
        """[(score, doc)] best first. Embeds any doc not seen before (once, then cached)."""
        docs = [d for d in docs if (text_of(d) or "").strip()]
        if not (query.strip() and docs):
            return []
        with self.lock:
            missing = list({_key(text_of(d)): text_of(d) for d in docs if _key(text_of(d)) not in self.vectors}.items())
        if missing:
            vecs = self._embed([t for _, t in missing], "RETRIEVAL_DOCUMENT")
            with self.lock:
                self.vectors.update({k: v for (k, _), v in zip(missing, vecs)})
                self._save()
        q = self._embed([query], "RETRIEVAL_QUERY")[0]
        with self.lock:
            scored = [(sum(a * b for a, b in zip(q, self.vectors[_key(text_of(d))])), d) for d in docs]
        scored.sort(key=lambda sd: -sd[0])
        return [(round(s, 3), d) for s, d in scored[:limit] if s >= min_score]
