import subprocess
from pathlib import Path


from execution import docker_runner as dr

JUNIT = """<testsuite><testcase name="test_a" time="0.01"/><testcase name="test_b" time="0.02"><failure message="assert 1 == 2">trace</failure></testcase>
<testcase name="test_c" time="0.0"><error message="boom"/></testcase><testcase name="test_d"><skipped message="x"/></testcase></testsuite>"""


def test_docker_command_hardening():
    cmd = dr.build_docker_command("/tmp/x", "cp-test")
    joined = " ".join(cmd)
    for flag in ("--network none", "--read-only", "--user 10001:10001", "--cap-drop ALL", "--security-opt no-new-privileges",
                 "--pids-limit", "--memory", "--cpus", "--tmpfs /tmp"):
        assert flag in joined, flag
    assert "docker.sock" not in joined
    assert "-v /tmp/x:/work:ro" in joined  # code mounted read-only
    env_flags = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-e"]
    assert all(not any(s in e.upper() for s in ("KEY", "SECRET", "TOKEN")) for e in env_flags)  # no secrets passed


def test_junit_parsing():
    outs = dr.parse_junit(JUNIT)
    assert [o.status for o in outs] == ["passed", "failed", "error", "skipped"]
    assert outs[1].message.startswith("assert 1 == 2")
    assert dr.parse_junit("not xml") == []


def test_unavailable_never_falls_back_to_local(monkeypatch):
    called = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: called.append(a) or None)
    res = dr.run_pytest("x = 1", "def test_x(): assert True")
    assert res.available is False and res.executed is False
    assert "NOT performed" in res.reason
    assert called == []  # nothing was executed at all


def test_check_docker_without_cli(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(dr.shutil, "which", lambda _: None)
    ok, reason = dr._check_docker_uncached()
    assert not ok and "not installed" in reason


def test_timeout_kills_container_and_cleans_up(monkeypatch):
    monkeypatch.setattr(dr, "check_docker", lambda max_age=15.0: (True, "ok"))
    created = []
    real_mkdtemp = dr.tempfile.mkdtemp
    monkeypatch.setattr(dr.tempfile, "mkdtemp", lambda **k: created.append(real_mkdtemp(**k)) or created[-1])
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd[:2])
        if cmd[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(cmd, 1)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(dr.subprocess, "run", fake_run)
    res = dr.run_pytest("while True: pass", "def test_x(): pass")
    assert res.timed_out and res.executed and "killed" in res.reason
    assert ["docker", "kill"] in calls
    assert created and not Path(created[0]).exists()  # temp workspace removed


def test_successful_run_parses_report_and_truncates(monkeypatch):
    monkeypatch.setattr(dr, "check_docker", lambda max_age=15.0: (True, "ok"))
    big = "x" * 300_000
    out = f"{big}\n{dr.JUNIT_MARKER}\n{JUNIT}\n{dr.JUNIT_MARKER}RC\n1\n"
    monkeypatch.setattr(dr.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, out, ""))
    res = dr.run_pytest("x=1", "def test_a(): pass")
    assert res.executed and res.truncated and len(res.stdout) < 200_000
    assert (res.passed, res.failed, res.exit_code) == (1, 2, 1)
