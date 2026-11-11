"""Central, environment-based configuration.

All model names, limits and paths are read here and nowhere else. Settings are
re-read from the environment on each call to ``get_settings()`` so tests (and the
Settings page) can change them at runtime.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

# Runtime overrides set from the Settings page (process-local, never persisted, never hold keys).
_overrides: dict[str, str] = {}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _env(name: str, default: str = "") -> str:
    return _overrides.get(name, os.getenv(name, default))


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    gemini_api_key: str
    groq_api_key: str
    gemini_model: str
    groq_model: str
    embedding_model: str
    llm_timeout: float
    database_url: str
    chroma_dir: str
    log_level: str
    rate_limit_per_minute: int
    max_code_bytes: int
    max_upload_bytes: int
    max_repair_attempts: int
    sandbox_image: str
    exec_timeout: int
    exec_memory: str
    exec_cpus: float
    exec_pids_limit: int
    exec_max_output_bytes: int
    allowed_extensions: tuple[str, ...] = (".py", ".java", ".c", ".h", ".txt")

    @property
    def active_model(self) -> str:
        return self.gemini_model if self.llm_provider == "gemini" else self.groq_model


def get_settings() -> Settings:
    provider = _env("LLM_PROVIDER", "gemini").strip().lower() or "none"
    return Settings(
        llm_provider=provider,
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
        gemini_model=_env("GEMINI_MODEL", "gemini-flash-latest"),
        groq_model=_env("GROQ_MODEL", "openai/gpt-oss-120b"),
        embedding_model=_env("EMBEDDING_MODEL", "gemini-embedding-2"),
        llm_timeout=_float("LLM_TIMEOUT_SECONDS", 60.0),
        database_url=os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'codepilot.db'}"),
        chroma_dir=os.getenv("CHROMA_DIR", str(ROOT / "data" / "chroma")),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        rate_limit_per_minute=_int("RATE_LIMIT_PER_MINUTE", 30),
        max_code_bytes=_int("MAX_CODE_BYTES", 200_000),
        max_upload_bytes=_int("MAX_UPLOAD_BYTES", 200_000),
        max_repair_attempts=min(_int("MAX_REPAIR_ATTEMPTS", 3), 3),  # hard cap of 3
        sandbox_image=os.getenv("SANDBOX_IMAGE", "codepilot-sandbox:latest"),
        exec_timeout=_int("EXEC_TIMEOUT_SECONDS", 30),
        exec_memory=os.getenv("EXEC_MEMORY", "256m"),
        exec_cpus=_float("EXEC_CPUS", 1.0),
        exec_pids_limit=_int("EXEC_PIDS_LIMIT", 64),
        exec_max_output_bytes=_int("EXEC_MAX_OUTPUT_BYTES", 100_000),
    )


def set_override(name: str, value: str) -> None:
    _overrides[name] = value


def clear_overrides() -> None:
    _overrides.clear()
