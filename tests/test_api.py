import time

import pytest

from agents import demo_data
from tests.helpers import FakeLLM, install_fake_llm

S = demo_data.SAMPLES["average_empty"]


def demo_body(**kw):
    return {"code": S["code"], "description": S["description"], "sample_id": "average_empty", "demo": True, **kw}


def test_health(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["sandbox"]["available"] is False and h["llm"]["configured"] is False
    assert "no-llm" in h["llm"]["mode"]


def test_review_and_history_roundtrip(client):                                  # scenario 16
    r = client.post("/api/review", json=demo_body())
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "completed" and d["analysis_mode"] == "demo_simulated" and d["issues"][0]["id"] == "BUG001"
    assert d["issues"][0]["source"] == "demo_simulated" and len(d["trace"]) >= 8
    lst = client.get("/api/reviews").json()
    assert lst["total"] == 1 and lst["items"][0]["issue_count"] == 1
    got = client.get(f"/api/reviews/{d['id']}").json()
    assert got["source_code"] == S["code"] and got["report"]["verification"]["status"] == "unverified_execution_unavailable"
    assert got["tests"] and all(t["status"] == "not_run" for t in got["tests"])
    st = client.get("/api/stats").json()
    assert st["total_reviews"] == 1 and st["bugs_identified"] == 1 and st["fixes_verified"] == 0 and st["tests_executed"] == 0
    assert client.delete(f"/api/reviews/{d['id']}").status_code == 204
    assert client.get(f"/api/reviews/{d['id']}").status_code == 404
    assert client.delete(f"/api/reviews/{d['id']}").status_code == 404
    assert client.get("/api/reviews").json()["total"] == 0


@pytest.mark.parametrize("path,intent", [("/api/debug", "DEBUG"), ("/api/explain", "EXPLAIN"), ("/api/generate-tests", "TEST"),
                                         ("/api/optimize", "OPTIMIZE"), ("/api/security-audit", "SECURITY_AUDIT")])
def test_specific_endpoints_force_intent(client, path, intent):
    d = client.post(path, json={"code": "def f(x):\n    return x\n"}).json()
    assert d["intent"] == intent


def test_auto_intent_on_review_endpoint(client):
    d = client.post("/api/review", json={"code": "def f(x):\n    return eval(x)\n", "description": "check for vulnerabilities"}).json()
    assert d["intent"] == "SECURITY_AUDIT" and any(i["category"] == "security" for i in d["issues"])


@pytest.mark.parametrize("body,code", [
    ({"code": ""}, 422), ({"code": "   "}, 422), ({"code": "x", "language": "cobol"}, 422), ({"code": "x", "intent": "HACK"}, 422),
    ({}, 422), ({"code": "x" * 250_000}, 413), ({"code": "a\x00b"}, 422),
])
def test_invalid_input(client, body, code):                                      # scenario 13
    assert client.post("/api/review", json=body).status_code == code


def test_syntax_error_code_is_reported_not_crashed(client):
    d = client.post("/api/review", json={"code": "def f(:\n"}).json()
    assert d["issues"][0]["title"] == "Syntax error" and d["issues"][0]["severity"] == "critical"


def test_background_mode_and_progress(client):
    r = client.post("/api/review", json={**demo_body(), "background": True})
    assert r.status_code == 202
    rid = r.json()["id"]
    for _ in range(60):
        d = client.get(f"/api/reviews/{rid}").json()
        if d["status"] != "running":
            break
        time.sleep(0.2)
    assert d["status"] == "completed" and d["trace"]


def test_upload_limits_and_types(client):
    assert client.post("/api/upload", files={"file": ("a.py", b"print(1)\n")}).json()["language"] == "python"
    assert client.post("/api/upload", files={"file": ("a.c", b"int x;")}).json()["language"] == "c"
    assert client.post("/api/upload", files={"file": ("a.exe", b"MZ")}).status_code == 415
    assert client.post("/api/upload", files={"file": ("a.py", b"x" * 250_000)}).status_code == 413
    assert client.post("/api/upload", files={"file": ("a.py", b"\xff\xfe")}).status_code == 422


def test_rate_limiting(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
    codes = [client.post("/api/review", json={"code": "x = 1\n", "run_validation": False}).status_code for _ in range(4)]
    assert codes[:2] == [200, 200] and 429 in codes[2:]
    assert client.get("/api/health").status_code == 200       # reads are not limited


def test_settings_never_expose_keys_and_can_switch(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSySECRETSECRETSECRET12345678")
    s = client.get("/api/settings").json()
    assert "SECRETSECRET" not in str(s) and s["gemini_key"].startswith("…") and s["configured"] is True
    r = client.put("/api/settings", json={"provider": "groq", "model": "some-model"}).json()
    assert r["provider"] == "groq" and r["model"] == "some-model" and r["configured"] is False   # no groq key
    assert client.put("/api/settings", json={"model": "bad model; rm -rf"}).status_code == 422


def test_full_llm_pipeline_via_api_with_fake_provider(client, monkeypatch, local_sandbox):
    from tests.helpers import BUGGY

    install_fake_llm(monkeypatch, FakeLLM())
    d = client.post("/api/debug", json={"code": BUGGY, "description": "binary search bug"}).json()
    assert d["verification_status"] == "verified" and d["tests"] and all(t["status"] == "passed" for t in d["tests"])
    assert d["issues"][0]["status"] == "resolved"
    assert client.get("/api/stats").json()["fixes_verified"] == 1


def test_samples_endpoint(client):
    s = client.get("/api/samples").json()
    assert {x["id"] for x in s} == set(demo_data.SAMPLES) and all("code" in x for x in s)


def test_internal_errors_do_not_leak(client, monkeypatch):
    from backend.services import review_service

    monkeypatch.setattr(review_service, "run_workflow", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret path /etc/x")))
    r = client.post("/api/review", json={"code": "x = 1\n"})
    assert r.status_code == 500 and "/etc/x" not in r.text
    assert client.get("/api/reviews").json()["items"][0]["status"] == "failed"
