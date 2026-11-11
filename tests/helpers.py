"""Test-only helpers. NOTE: `local_run_pytest` runs repository-authored test fixtures locally and exists ONLY so the
validator/repair logic can be exercised without a Docker daemon. The product never does this for user code."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from agents.llm import LLMProvider
from execution.docker_runner import ExecutionResult, parse_junit

BUGGY = '''def binary_search(items, target):
    """Index of target or -1."""
    low, high = 0, len(items) - 1
    while low < high:
        mid = (low + high) // 2
        if items[mid] == target:
            return mid
        if items[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1
'''
GOOD_FIX = BUGGY.replace("while low < high:", "while low <= high:")
WRONG_FIX = 'def binary_search(items, target):\n    """Index of target or -1."""\n    return -1\n'
TESTS = '''from solution import binary_search


def test_single():
    assert binary_search([5], 5) == 0


def test_last():
    assert binary_search([1, 3, 5, 7], 7) == 3


def test_missing():
    assert binary_search([1, 3], 2) == -1
'''
TEST_META = [
    {"name": "test_single", "description": "one element", "category": "boundary", "expected": "0", "covers": ["BUG001"]},
    {"name": "test_last", "description": "last element", "category": "boundary", "expected": "3", "covers": ["BUG001"]},
    {"name": "test_missing", "description": "absent", "category": "normal", "expected": "-1", "covers": []},
]


def local_run_pytest(solution_code: str, test_code: str) -> ExecutionResult:
    t0 = time.monotonic()
    with tempfile.TemporaryDirectory() as d:
        Path(d, "solution.py").write_text(solution_code)
        Path(d, "test_solution.py").write_text(test_code)
        p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={d}/r.xml", d],
                           capture_output=True, text=True, timeout=60, cwd=d)
        xml = Path(d, "r.xml").read_text() if Path(d, "r.xml").exists() else ""
    return ExecutionResult(available=True, executed=True, exit_code=p.returncode, duration_s=time.monotonic() - t0,
                           tests=parse_junit(xml), stdout=p.stdout)


class FakeLLM(LLMProvider):
    """Scripted provider: routes on the agent's system prompt. `fixes` is consumed one per Fixer call."""
    name = "fake"

    def __init__(self, fixes=None, bug_issues=None, fail_on=(), intent="DEBUG"):
        super().__init__("fake-model", "k", 1.0)
        self.fixes = list(fixes if fixes is not None else [GOOD_FIX])
        self.calls: list[str] = []
        self.fail_on = fail_on
        self.intent = intent
        self.bug_issues = bug_issues if bug_issues is not None else [
            {"title": "Loop skips last candidate", "severity": "high", "line_number": 4, "description": "low < high", "suggested_fix": "use <=",
             "confidence": 0.9, "category": "bug"},
            {"title": "Imaginary issue", "severity": "low", "line_number": 999, "description": "bad line", "suggested_fix": "", "confidence": 0.4, "category": "bug"},
        ]

    def generate(self, system: str, user: str) -> str:
        from agents.llm import LLMError

        for key in ("Bug Finder", "Fixer", "Test Writer", "Style and Quality", "classify", "executive summary", "explaining"):
            if key in system:
                self.calls.append(key)
                if key in self.fail_on:
                    raise LLMError(f"simulated outage in {key}")
                break
        if "Bug Finder" in system:
            return json.dumps({"issues": self.bug_issues})
        if "Style and Quality" in system:
            return json.dumps({"issues": [], "recommendations": ["Add type hints."]})
        if "Fixer" in system:
            code = self.fixes[min(len([c for c in self.calls if c == "Fixer"]) - 1, len(self.fixes) - 1)]
            return json.dumps({"corrected_code": code, "changes": [{"description": "changed loop", "reason": "boundary"}]})
        if "Test Writer" in system:
            return json.dumps({"test_code": TESTS, "tests": TEST_META})
        if "classify" in system:
            return json.dumps({"intent": self.intent, "confidence": 0.9, "reasoning": "fake"})
        if "executive summary" in system:
            return json.dumps({"summary": "Fake summary of the review."})
        if "explaining" in system:
            return json.dumps({"explanation": "It searches.", "complexity": "O(log n)", "key_points": ["halves the range"]})
        return "{}"


MODULES = ["agents.intent_router", "agents.bug_finder", "agents.style_agent", "agents.fixer_agent", "agents.test_writer",
           "agents.report_agent", "agents.explain_agent"]


def install_fake_llm(monkeypatch, fake: LLMProvider | None):
    import importlib

    for m in MODULES:
        monkeypatch.setattr(importlib.import_module(m), "get_provider", lambda f=fake: f)
