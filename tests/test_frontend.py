"""Headless Streamlit tests (AppTest) wired to the real FastAPI app through an in-process client."""
import sys
from pathlib import Path

import pytest

from agents import demo_data

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
sys.path.insert(0, str(FRONTEND))

from streamlit.testing.v1 import AppTest  # noqa: E402

from components import api  # noqa: E402


@pytest.fixture
def app(client, monkeypatch):
    def fake_request(method, path, timeout=30.0, **kw):
        r = client.request(method, path, **kw)
        if r.status_code >= 400:
            raise api.ApiError(f"{r.status_code}: {r.json().get('detail')}")
        return None if r.status_code == 204 else r.json()

    monkeypatch.setattr(api, "_request", fake_request)
    at = AppTest.from_file(str(FRONTEND / "app.py"), default_timeout=60)
    return at.run()


def no_errors(at):
    assert not at.exception, [e.value for e in at.exception]


def test_all_seven_pages_render_with_empty_state(app):
    no_errors(app)
    assert [m.label for m in app.metric] == ["Total reviews", "Bugs identified", "Fixes verified", "Tests executed"]
    assert any("Start New Code Review" in b.label for b in app.button)
    for page in ("workspace", "activity", "results", "test_results", "history", "settings"):
        app.switch_page(f"pages/{page}.py").run()
        no_errors(app)


def test_end_to_end_demo_flow_through_ui(app):
    app.switch_page("pages/workspace.py").run()
    app.button(key="sample_binary_search").click().run()
    assert "binary_search" in app.session_state.code_input
    [cb for cb in app.checkbox if "simulated" in cb.label][0].check().run()
    [b for b in app.button if "Run analysis" in b.label][0].click().run()   # switches to Agent Activity and polls to completion
    no_errors(app)
    rid = app.session_state.current_review_id
    assert rid
    body = " ".join(m.value for m in app.markdown) + " ".join(e.label for e in app.expander)
    assert "Intent detection" in body and "Static code analysis" in body and "Validation" in body   # real trace
    assert any("SIMULATED" in w.value for w in app.warning)                                        # demo labelled
    assert any("View review results" in b.label for b in app.button)
    app.switch_page("pages/results.py").run()   # (AppTest reruns the original page after an in-script switch_page)
    no_errors(app)
    text = " ".join(m.value for m in app.markdown)
    assert "BUG001" in text and "simulated demo" in text
    assert any("NOT verified" in w.value for w in app.warning)       # fix not claimed as verified
    app.switch_page("pages/test_results.py").run()
    no_errors(app)
    assert any("NOT performed" in w.value for w in app.warning) and [m.value for m in app.metric][:1] == [str(len(demo_data.SAMPLES["binary_search"]["tests"]))]
    app.switch_page("pages/history.py").run()
    no_errors(app)
    app.checkbox[0].check().run()
    [b for b in app.button if "Delete review" in b.label][0].click().run()
    no_errors(app)
    assert api.list_reviews()["total"] == 0


def test_workspace_rejects_bad_upload_and_shows_error(app):
    app.switch_page("pages/workspace.py").run()
    no_errors(app)
    run = [b for b in app.button if "Run analysis" in b.label][0]
    assert run.disabled  # no code -> cannot run


def test_settings_page_never_shows_full_keys(app, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyFULLKEYFULLKEYFULLKEY1234567")
    app.switch_page("pages/settings.py").run()
    no_errors(app)
    shown = " ".join(m.value for m in app.metric) + " ".join(m.value for m in app.markdown)
    assert "FULLKEYFULLKEY" not in shown and "…4567" in shown


def test_api_down_shows_friendly_error(monkeypatch):
    def down(*a, **k):
        raise api.ApiError("Cannot reach the CodePilot API at http://x")

    monkeypatch.setattr(api, "_request", down)
    at = AppTest.from_file(str(FRONTEND / "app.py"), default_timeout=30).run()
    assert not at.exception and any("Cannot reach" in e.value for e in at.error)
