import pytest

from backend.core import config


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path_factory, tmp_path):
    """No real keys, temp DB + vector store, deterministic Docker status, clean overrides."""
    for k in ("GEMINI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path_factory.getbasetemp() / "chroma"))
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1000")
    config.clear_overrides()
    from backend.core.rate_limit import reset_rate_limiter

    reset_rate_limiter()
    from execution import docker_runner

    monkeypatch.setattr(docker_runner, "check_docker", lambda max_age=15.0: (False, "Docker daemon is not running (test default)."))
    yield
    config.clear_overrides()


@pytest.fixture
def db_url(tmp_path):
    from backend.database import db

    url = f"sqlite:///{tmp_path / 'test.db'}"
    db.configure(url)
    db.init_db()
    return url


@pytest.fixture
def client(db_url):
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def local_sandbox(monkeypatch):
    """Route the validator through the test-only local pytest runner (stands in for Docker)."""
    from agents import validator
    from tests.helpers import local_run_pytest

    monkeypatch.setattr(validator.docker_runner, "run_pytest", local_run_pytest)
