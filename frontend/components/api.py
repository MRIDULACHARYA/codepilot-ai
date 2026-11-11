"""Thin HTTP client for the CodePilot AI backend."""
from __future__ import annotations

import os

import httpx

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")


class ApiError(RuntimeError):
    pass


def _request(method: str, path: str, timeout: float = 30.0, **kw):
    try:
        r = httpx.request(method, f"{API_URL}{path}", timeout=timeout, **kw)
    except httpx.ConnectError as exc:
        raise ApiError(f"Cannot reach the CodePilot API at {API_URL}. Start it with: uvicorn backend.main:app") from exc
    except httpx.HTTPError as exc:
        raise ApiError(f"API request failed ({type(exc).__name__}).") from exc
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        raise ApiError(f"{r.status_code}: {detail}")
    return None if r.status_code == 204 else r.json()


def health() -> dict:
    return _request("GET", "/api/health", timeout=15)


def stats() -> dict:
    return _request("GET", "/api/stats")


def samples() -> list[dict]:
    return _request("GET", "/api/samples")


def submit_review(payload: dict) -> dict:
    return _request("POST", "/api/review", json={**payload, "background": True})


def get_review(review_id: str) -> dict:
    return _request("GET", f"/api/reviews/{review_id}")


def list_reviews(limit: int = 100) -> dict:
    return _request("GET", "/api/reviews", params={"limit": limit})


def delete_review(review_id: str) -> None:
    _request("DELETE", f"/api/reviews/{review_id}")


def upload(filename: str, content: bytes) -> dict:
    return _request("POST", "/api/upload", files={"file": (filename, content)})


def get_settings() -> dict:
    return _request("GET", "/api/settings")


def put_settings(provider: str | None, model: str | None) -> dict:
    return _request("PUT", "/api/settings", json={"provider": provider, "model": model})
