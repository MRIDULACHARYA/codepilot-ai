"""Isolated pytest execution in Docker.

Security properties of every run (see ``build_docker_command``):
  * non-root user, all capabilities dropped, no-new-privileges
  * network disabled
  * read-only root filesystem; only a small tmpfs at /tmp is writable
  * CPU, memory and process-count limits; wall-clock timeout (container is killed)
  * code lives in a fresh temp dir mounted READ-ONLY, deleted afterwards
  * the container gets NO environment variables from the host and no Docker socket
  * output is truncated to a byte limit

If Docker (or the sandbox image) is unavailable, execution is DISABLED and the result
says so. There is deliberately NO fallback to running user code on the host.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

from backend.core.config import get_settings
from backend.core.logging import get_logger

log = get_logger("execution")

JUNIT_MARKER = "===CODEPILOT_JUNIT==="
UNAVAILABLE_NOTE = "Docker sandbox unavailable: verification was NOT performed."


@dataclass
class TestOutcome:
    name: str
    status: str  # passed | failed | error | skipped
    duration_s: float = 0.0
    message: str = ""


@dataclass
class ExecutionResult:
    available: bool
    executed: bool = False
    reason: str = ""
    timed_out: bool = False
    exit_code: int | None = None
    duration_s: float = 0.0
    tests: list[TestOutcome] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    truncated: bool = False

    @property
    def passed(self) -> int:
        return sum(1 for t in self.tests if t.status == "passed")

    @property
    def failed(self) -> int:
        return sum(1 for t in self.tests if t.status in ("failed", "error"))

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(passed=self.passed, failed=self.failed, total=len(self.tests))
        return d


def unavailable(reason: str) -> ExecutionResult:
    return ExecutionResult(available=False, executed=False, reason=f"{UNAVAILABLE_NOTE} {reason}")


_cache: dict = {"t": 0.0, "v": None}


def check_docker(max_age: float = 15.0) -> tuple[bool, str]:
    """Return (usable, reason). Result is cached briefly because `docker info` can be slow."""
    now = time.monotonic()
    if _cache["v"] is not None and now - _cache["t"] < max_age:
        return _cache["v"]
    _cache["v"] = _check_docker_uncached()
    _cache["t"] = now
    return _cache["v"]


def _check_docker_uncached() -> tuple[bool, str]:
    s = get_settings()
    if shutil.which("docker") is None:
        return False, "the `docker` CLI is not installed."
    try:
        info = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True, text=True, timeout=8, env=_client_env(),
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"Docker daemon not reachable ({type(exc).__name__})."
    if info.returncode != 0:
        return False, "Docker daemon is not running or not reachable."
    img = subprocess.run(
        ["docker", "image", "inspect", s.sandbox_image],
        capture_output=True, text=True, timeout=8, env=_client_env(),
    )
    if img.returncode != 0:
        return False, (
            f"sandbox image '{s.sandbox_image}' not found; build it with scripts/build_sandbox.sh."
        )
    return True, "ok"


def _client_env() -> dict[str, str]:
    """Environment for the docker *client* process only (no application secrets)."""
    import os

    keep = ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONFIG", "DOCKER_CONTEXT", "XDG_RUNTIME_DIR")
    return {k: os.environ[k] for k in keep if k in os.environ}


def build_docker_command(workdir: str, container_name: str) -> list[str]:
    s = get_settings()
    inner = (
        f"python -m pytest -q -p no:cacheprovider --junitxml=/tmp/report.xml --maxfail=50 /work "
        f"> /tmp/out.txt 2>&1; echo $? > /tmp/rc.txt; cat /tmp/out.txt; "
        f"echo {JUNIT_MARKER}; cat /tmp/report.xml 2>/dev/null; echo; echo {JUNIT_MARKER}RC; cat /tmp/rc.txt"
    )
    return [
        "docker", "run", "--rm",
        "--name", container_name,
        "--network", "none",
        "--read-only",
        "--tmpfs", "/tmp:rw,size=64m",
        "--user", "10001:10001",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--cpus", str(s.exec_cpus),
        "--memory", s.exec_memory,
        "--memory-swap", s.exec_memory,
        "--pids-limit", str(s.exec_pids_limit),
        "--ulimit", "nofile=256:256",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", "HOME=/tmp",
        "-v", f"{workdir}:/work:ro",
        "-w", "/work",
        s.sandbox_image,
        "sh", "-c", inner,
    ]


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text.encode("utf-8", errors="ignore")) <= limit:
        return text, False
    return text.encode("utf-8", errors="ignore")[:limit].decode("utf-8", errors="ignore") + "\n…[output truncated]", True


def parse_junit(xml_text: str) -> list[TestOutcome]:
    outcomes: list[TestOutcome] = []
    if not xml_text.strip():
        return outcomes
    try:
        root = ET.fromstring(xml_text.strip())
    except ET.ParseError:
        return outcomes
    for case in root.iter("testcase"):
        name = case.get("name", "?")
        dur = float(case.get("time", 0) or 0)
        status, msg = "passed", ""
        for child in case:
            if child.tag == "failure":
                status, msg = "failed", (child.get("message") or child.text or "")[:2000]
            elif child.tag == "error":
                status, msg = "error", (child.get("message") or child.text or "")[:2000]
            elif child.tag == "skipped":
                status, msg = "skipped", (child.get("message") or "")[:500]
        outcomes.append(TestOutcome(name=name, status=status, duration_s=dur, message=msg))
    return outcomes


def run_pytest(solution_code: str, test_code: str) -> ExecutionResult:
    """Run ``test_code`` against ``solution_code`` (module name: ``solution``) in the sandbox."""
    s = get_settings()
    ok, reason = check_docker()
    if not ok:
        return unavailable(reason)

    tmp = tempfile.mkdtemp(prefix="codepilot_")
    name = f"codepilot-{uuid.uuid4().hex[:12]}"
    started = time.monotonic()
    try:
        Path(tmp, "solution.py").write_text(solution_code, encoding="utf-8")
        Path(tmp, "test_solution.py").write_text(test_code, encoding="utf-8")
        # Container user is uid 10001; make the read-only mount traversable.
        Path(tmp).chmod(0o755)
        for f in Path(tmp).iterdir():
            f.chmod(0o644)
        cmd = build_docker_command(tmp, name)
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=s.exec_timeout, env=_client_env()
            )
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", name], capture_output=True, timeout=10, env=_client_env())
            log.warning("sandbox timeout", extra={"container": name})
            return ExecutionResult(
                available=True, executed=True, timed_out=True,
                reason=f"Execution exceeded {s.exec_timeout}s and was killed.",
                duration_s=time.monotonic() - started,
            )
        raw = proc.stdout
        rc_marker = f"{JUNIT_MARKER}RC"
        rc = None
        if rc_marker in raw:
            raw, rc_part = raw.split(rc_marker, 1)
            try:
                rc = int(rc_part.strip().splitlines()[0])
            except (ValueError, IndexError):
                rc = None
        console, _, junit = raw.partition(JUNIT_MARKER)
        tests = parse_junit(junit)
        out, trunc = _truncate(console, s.exec_max_output_bytes)
        err, trunc2 = _truncate(proc.stderr, s.exec_max_output_bytes)
        reason_txt = ""
        if proc.returncode != 0 and not tests:
            reason_txt = "No test report was produced (collection error, import error, or sandbox failure)."
        return ExecutionResult(
            available=True, executed=True, reason=reason_txt, exit_code=rc if rc is not None else proc.returncode,
            duration_s=time.monotonic() - started, tests=tests, stdout=out, stderr=err, truncated=trunc or trunc2,
        )
    except Exception as exc:  # pragma: no cover - defensive
        log.exception("sandbox error")
        return ExecutionResult(available=True, executed=False, reason=f"Sandbox error: {type(exc).__name__}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
