"""Agentic retrieval: decide WHETHER and WHAT to retrieve from intent + agent need, then query Chroma.

Nothing is fabricated: results are real chunks with their source file and section. If the embedding
API is down the local hashing embedder is used and the retrieval method is reported as such.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.core.logging import get_logger
from rag import ingestion
from rag.embeddings import EmbeddingUnavailable, HashEmbedder, get_embedder

log = get_logger("rag.retriever")

# intent -> knowledge categories worth retrieving ([] = do not retrieve)
INTENT_CATEGORIES: dict[str, list[str]] = {
    "DEBUG": ["debugging", "runtime_errors", "data_structures", "language_standard"],
    "REVIEW": ["language_standard", "debugging", "testing"],
    "EXPLAIN": ["language_standard", "data_structures"],
    "TEST": ["testing"],
    "OPTIMIZE": ["complexity", "data_structures"],
    "SECURITY_AUDIT": ["security", "runtime_errors"],
}
MAX_DISTANCE = 1.15  # cosine distance above which a hit is considered irrelevant and dropped


@dataclass
class RetrievalResult:
    performed: bool
    reason: str
    method: str = ""
    contexts: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"performed": self.performed, "reason": self.reason, "method": self.method, "contexts": self.contexts}


def plan_retrieval(intent: str, code: str, language: str) -> tuple[list[str], str]:
    """Decide if retrieval is needed. Returns (categories, reason)."""
    cats = INTENT_CATEGORIES.get(intent, ["language_standard"])
    if not cats:
        return [], f"intent {intent} needs no external knowledge"
    if len(code.strip().splitlines()) < 2 and intent in ("EXPLAIN", "TEST"):
        return [], "trivially short input: retrieval skipped"
    return cats, f"intent {intent} -> categories {cats}"


def _ensure_ingested(embedder) -> None:
    client = ingestion.get_client()
    name = ingestion.collection_name(embedder.id)
    try:
        col = client.get_collection(name)
        if col.count() > 0:
            return
    except Exception:
        pass
    ingestion.ingest()


def retrieve(intent: str, code: str, language: str = "python", query_hint: str = "", k: int = 4) -> RetrievalResult:
    cats, reason = plan_retrieval(intent, code, language)
    if not cats:
        return RetrievalResult(False, reason)
    query = f"{intent.lower()} {language} {query_hint}\n{code[:1500]}"
    embedder = get_embedder()
    try:
        _ensure_ingested(embedder)
        vec = embedder.embed([query])[0]
    except EmbeddingUnavailable as exc:
        log.warning("embedding API unavailable; falling back to local embeddings", extra={"error": str(exc)})
        embedder = HashEmbedder()
        _ensure_ingested(embedder)
        vec = embedder.embed([query])[0]
    except Exception as exc:
        log.warning("retrieval failed", extra={"error": str(exc)[:200]})
        return RetrievalResult(False, f"retrieval unavailable ({type(exc).__name__}); continuing without context")

    col = ingestion.get_client().get_collection(ingestion.collection_name(embedder.id))
    lang_filter = {"$in": [language.lower(), "any"]}
    where = {"$and": [{"category": {"$in": cats}}, {"language": lang_filter}]}
    try:
        res = col.query(query_embeddings=[vec], n_results=k, where=where)
    except Exception as exc:
        log.warning("chroma query failed", extra={"error": str(exc)[:200]})
        return RetrievalResult(False, f"vector query failed ({type(exc).__name__})")
    contexts = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0], strict=True):
        if dist > MAX_DISTANCE:
            continue
        contexts.append({
            "text": doc, "source": meta["source"], "section": meta["section"], "title": meta["title"],
            "category": meta["category"], "distance": round(float(dist), 4),
        })
    return RetrievalResult(True, reason, method=embedder.label, contexts=contexts)


def format_context(contexts: list[dict], max_chars: int = 3500) -> str:
    """Render retrieved chunks for a prompt (inside untrusted-data delimiters by the caller)."""
    from backend.core.security import neutralize_delimiters

    out, used = [], 0
    for c in contexts:
        block = f"[{c['source']} § {c['section']}]\n{neutralize_delimiters(c['text'])}"
        if used + len(block) > max_chars:
            break
        out.append(block)
        used += len(block)
    return "\n\n".join(out) if out else "(no reference documents retrieved)"
