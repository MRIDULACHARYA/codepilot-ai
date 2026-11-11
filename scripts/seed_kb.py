"""Ingest the knowledge base into ChromaDB (also happens lazily on first retrieval).  python scripts/seed_kb.py [--force]"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rag.ingestion import ingest  # noqa: E402

print(json.dumps(ingest(force="--force" in sys.argv), indent=2))
