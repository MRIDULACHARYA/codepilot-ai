"""Knowledge-base ingestion: load -> extract text -> chunk -> embed -> store in ChromaDB.

Each markdown file begins with a front-matter block::

    ---
    category: debugging | runtime_errors | data_structures | complexity | security | testing | language_standard
    language: python | java | c | any
    title: Human readable title
    ---
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import chromadb

from backend.core.config import get_settings
from backend.core.logging import get_logger
from rag.embeddings import EmbeddingUnavailable, HashEmbedder, get_embedder

log = get_logger("rag.ingestion")
KB_DIR = Path(__file__).parent / "knowledge_base"
CHUNK_CHARS = 900
OVERLAP = 120


def parse_document(path: Path) -> dict:
    """Text extraction: split front matter from body."""
    raw = path.read_text(encoding="utf-8")
    meta = {"category": "general", "language": "any", "title": path.stem}
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
    body = raw
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = m.group(2)
    return {"source": path.name, "meta": meta, "text": body.strip()}


def chunk_document(doc: dict) -> list[dict]:
    """Chunk by markdown section, then by size with overlap. Keeps the section heading as a reference."""
    sections = re.split(r"(?m)^(?=#{1,3} )", doc["text"])
    chunks: list[dict] = []
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        heading = sec.splitlines()[0].lstrip("# ").strip() if sec.startswith("#") else doc["meta"]["title"]
        start = 0
        while start < len(sec):
            piece = sec[start : start + CHUNK_CHARS]
            chunks.append({"text": piece, "section": heading})
            if start + CHUNK_CHARS >= len(sec):
                break
            start += CHUNK_CHARS - OVERLAP
    for i, c in enumerate(chunks):
        c["id"] = hashlib.sha1(f"{doc['source']}:{i}:{c['text']}".encode()).hexdigest()[:16]
        c["source"] = doc["source"]
        c["category"] = doc["meta"]["category"]
        c["language"] = doc["meta"]["language"]
        c["title"] = doc["meta"]["title"]
    return chunks


def get_client() -> chromadb.ClientAPI:
    Path(get_settings().chroma_dir).mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=get_settings().chroma_dir)


def collection_name(embedder_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_\-]", "_", embedder_id)[:40]
    return f"codepilot_kb_{safe}"


def ingest(kb_dir: Path = KB_DIR, force: bool = False) -> dict:
    """Ingest all KB documents. Falls back to the local embedder if the embedding API fails."""
    embedder = get_embedder()
    docs = [parse_document(p) for p in sorted(kb_dir.glob("*.md"))]
    chunks = [c for d in docs for c in chunk_document(d)]
    if not chunks:
        return {"documents": 0, "chunks": 0, "embedder": embedder.id}
    texts = [c["text"] for c in chunks]
    try:
        vectors = embedder.embed(texts)
    except EmbeddingUnavailable as exc:
        log.warning("embedding API unavailable, using local fallback", extra={"error": str(exc)})
        embedder = HashEmbedder()
        vectors = embedder.embed(texts)
    client = get_client()
    name = collection_name(embedder.id)
    if force:
        try:
            client.delete_collection(name)
        except Exception:
            pass
    col = client.get_or_create_collection(name, metadata={"hnsw:space": "cosine"}, embedding_function=None)
    col.upsert(
        ids=[c["id"] for c in chunks],
        documents=texts,
        embeddings=vectors,
        metadatas=[{k: c[k] for k in ("source", "section", "category", "language", "title")} for c in chunks],
    )
    log.info("knowledge base ingested", extra={"documents": len(docs), "chunks": len(chunks), "embedder": embedder.id})
    return {"documents": len(docs), "chunks": len(chunks), "embedder": embedder.id, "collection": name}
