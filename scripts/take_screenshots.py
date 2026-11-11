"""Capture README screenshots from a RUNNING app (API on :8000, Streamlit on :8501).

    python scripts/take_screenshots.py            # requires: pip install playwright (uses the system Chrome)
"""
import shutil
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
BASE = "http://localhost:8501"
CHROME = shutil.which("google-chrome") or shutil.which("chromium")


def nav(page, label):
    page.get_by_role("link", name=label).first.click()
    page.wait_for_timeout(2500)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(BASE)
        page.wait_for_selector("text=Your autonomous AI software engineering team", timeout=30000)
        page.wait_for_timeout(2000)
        page.screenshot(path=OUT / "01_dashboard_empty.png")

        nav(page, "Code Review Workspace")
        page.get_by_text("Demo samples").first.click()
        page.wait_for_timeout(800)
        page.get_by_role("button", name="Binary search skips the last candidate").click()
        page.wait_for_timeout(1500)
        page.get_by_text("Use simulated demo analysis").click()
        page.wait_for_timeout(800)
        page.screenshot(path=OUT / "02_workspace.png")
        page.get_by_role("button", name="Run analysis").click()
        page.wait_for_selector("text=View review results", timeout=60000)
        page.wait_for_timeout(1000)
        page.screenshot(path=OUT / "03_agent_activity.png")

        nav(page, "Review Results")
        page.wait_for_selector("text=Quality score", timeout=20000)
        page.screenshot(path=OUT / "04_review_results.png", full_page=True)
        page.get_by_role("tab", name="Corrected code").click()
        page.wait_for_timeout(1000)
        page.screenshot(path=OUT / "05_corrected_code.png")

        nav(page, "Test Results")
        page.wait_for_timeout(1500)
        page.screenshot(path=OUT / "06_test_results.png", full_page=True)
        nav(page, "Review History")
        page.wait_for_timeout(1500)
        page.screenshot(path=OUT / "07_history.png", full_page=True)
        nav(page, "Settings")
        page.wait_for_timeout(1500)
        page.screenshot(path=OUT / "08_settings.png", full_page=True)
        nav(page, "Dashboard")
        page.wait_for_timeout(2000)
        page.screenshot(path=OUT / "09_dashboard.png", full_page=True)
        browser.close()
    print("saved", sorted(f.name for f in OUT.iterdir()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
