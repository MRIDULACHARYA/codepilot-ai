"""Input validation, secret redaction and prompt-injection detection."""
from __future__ import annotations

import os
import re

from backend.core.config import get_settings

SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),  # Google API keys
    re.compile(r"gsk_[0-9A-Za-z]{20,}"),  # Groq keys
    re.compile(r"sk-[0-9A-Za-z_\-]{20,}"),  # generic sk- keys
    re.compile(r"(?i)(api[_-]?key|secret|token|password)(\s*[=:]\s*)(['\"]?)[^\s'\",]{6,}\3"),
    re.compile(r"(?i)bearer\s+[0-9A-Za-z._\-]{16,}"),
]

INJECTION_PATTERNS = [
    re.compile(r"(?i)ignore (all |any )?(previous|prior|above) (instructions|prompts?)"),
    re.compile(r"(?i)disregard (the )?(system|previous) (prompt|instructions)"),
    re.compile(r"(?i)you are now (a|an|in)\b"),
    re.compile(r"(?i)(reveal|print|show|leak) (the |your )?(system prompt|api key|secrets?)"),
    re.compile(r"(?i)</?(untrusted_code|reference_docs|system)>"),
    re.compile(r"(?i)\bnew instructions?\s*:"),
    re.compile(r"(?i)report (no|zero) (bugs|issues)"),
]


class ValidationError(ValueError):
    """Raised for invalid user input (mapped to HTTP 422/400/413)."""

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


def redact(text: str) -> str:
    """Mask anything that looks like a credential, plus any configured key values."""
    if not text:
        return text
    out = text
    for key_name in ("GEMINI_API_KEY", "GROQ_API_KEY"):
        val = os.getenv(key_name, "")
        if len(val) >= 8:
            out = out.replace(val, "***REDACTED***")
    for pat in SECRET_PATTERNS:
        if pat.groups >= 3:
            out = pat.sub(lambda m: f"{m.group(1)}{m.group(2)}***REDACTED***", out)
        else:
            out = pat.sub("***REDACTED***", out)
    return out


def mask_key(key: str) -> str:
    """Never display a complete key: show only the last 4 characters."""
    if not key:
        return "not set"
    return f"…{key[-4:]}" if len(key) > 8 else "set"


def validate_code(code: str) -> str:
    s = get_settings()
    if code is None or not code.strip():
        raise ValidationError("Source code must not be empty.")
    if "\x00" in code:
        raise ValidationError("Source code contains NUL bytes; binary input is not supported.")
    if len(code.encode("utf-8", errors="ignore")) > s.max_code_bytes:
        raise ValidationError(
            f"Source code exceeds the {s.max_code_bytes} byte limit.", status_code=413
        )
    return code


def validate_upload(filename: str, content: bytes) -> str:
    """Validate an uploaded file and return its decoded text."""
    s = get_settings()
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in s.allowed_extensions:
        raise ValidationError(
            f"File type '{ext or 'unknown'}' is not allowed. Allowed: {', '.join(s.allowed_extensions)}",
            status_code=415,
        )
    if len(content) > s.max_upload_bytes:
        raise ValidationError(f"File exceeds the {s.max_upload_bytes} byte limit.", status_code=413)
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("File is not valid UTF-8 text.") from exc
    return validate_code(text)


def detect_prompt_injection(text: str) -> list[str]:
    """Return the patterns matched. Used to warn the model and the user; never to obey."""
    hits = []
    for pat in INJECTION_PATTERNS:
        m = pat.search(text or "")
        if m:
            hits.append(m.group(0)[:80])
    return hits


def neutralize_delimiters(text: str) -> str:
    """Stop submitted content from closing our untrusted-data delimiters."""
    return re.sub(r"(?i)<(/?)(untrusted_code|reference_docs|system)>", r"<\1_\2_>", text or "")
