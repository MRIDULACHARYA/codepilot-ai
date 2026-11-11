"""Embedding backends with an offline fallback.

* ``GeminiEmbedder``  - used when a Gemini key is configured (network call, with timeout).
* ``HashEmbedder``    - deterministic, local, dependency-free (hashed word/bigram features).
                        Used when no key is set or the embedding API fails. Quality is lexical,
                        not semantic, and results are labelled accordingly.

Embeddings of different backends are never mixed: each backend gets its own Chroma collection.
"""
from __future__ import annotations

import hashlib
import math
import re

import httpx

from backend.core.config import get_settings
from backend.core.logging import get_logger

log = get_logger("rag.embeddings")
DIM = 384
_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]+|\d+")
_STOP = {"the", "a", "an", "of", "to", "and", "or", "in", "is", "it", "for", "on", "with", "as", "be", "this", "that"}


class EmbeddingUnavailable(RuntimeError):
    pass


class HashEmbedder:
    id = "hash384"
    label = "local hashing fallback (lexical similarity)"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    @staticmethod
    def _one(text: str) -> list[float]:
        toks = [t.lower() for t in _TOKEN.findall(text) if t.lower() not in _STOP]
        feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False)]
        vec = [0.0] * DIM
        for f in feats:
            h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "big")
            vec[h % DIM] += 1.0 if (h >> 63) & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class GeminiEmbedder:
    label = "Gemini embeddings API"

    def __init__(self):
        s = get_settings()
        self.model, self.key, self.timeout = s.embedding_model, s.gemini_api_key, min(s.llm_timeout, 30.0)
        self.id = f"gemini-{self.model}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:batchEmbedContents"
        out: list[list[float]] = []
        for i in range(0, len(texts), 50):
            batch = texts[i : i + 50]
            payload = {"requests": [{"model": f"models/{self.model}", "content": {"parts": [{"text": t}]}} for t in batch]}
            try:
                r = httpx.post(url, headers={"x-goog-api-key": self.key}, json=payload, timeout=self.timeout)
                r.raise_for_status()
                out += [e["values"] for e in r.json()["embeddings"]]
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                raise EmbeddingUnavailable(f"Gemini embedding call failed: {type(exc).__name__}") from exc
        return out


def get_embedder():
    s = get_settings()
    if s.gemini_api_key and s.llm_provider == "gemini":
        return GeminiEmbedder()
    return HashEmbedder()
