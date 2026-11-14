"""Developer Lab tests — workspace confinement + the execution approval gate.

The security-critical behaviours are tested deterministically: code never runs
without explicit confirmation, paths can't escape the workspace, and destructive
commands are blocked by default.
"""
import pytest

from modules.developer_lab.workspace import Workspace, WorkspaceError
from modules.developer_lab.executor import ExecutionManager, scan_dangerous
from modules.developer_lab.assistant import pick_coding_model


# -- workspace confinement -------------------------------------------------- #
def test_list_and_read(tmp_path):
    ws = Workspace(tmp_path)
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    names = [e.name for e in ws.list_dir("")]
    assert "a.txt" in names
    assert ws.read_file("a.txt") == "hello"


def test_path_traversal_blocked(tmp_path):
    ws = Workspace(tmp_path)
    with pytest.raises(WorkspaceError):
        ws.read_file("../../etc/passwd")
    with pytest.raises(WorkspaceError):
        ws.list_dir("..")


def test_write_confined(tmp_path):
    ws = Workspace(tmp_path)
    n = ws.write_file("sub/new.py", "print(1)\n")
    assert n > 0
    assert (tmp_path / "sub" / "new.py").exists()
    with pytest.raises(WorkspaceError):
        ws.write_file("../escape.txt", "x")


def test_search(tmp_path):
    ws = Workspace(tmp_path)
    ws.write_file("code.py", "def run_pump():\n    return 42\n")
    hits = ws.search("run_pump")
    assert hits and hits[0]["path"] == "code.py"


# -- execution approval gate ------------------------------------------------ #
def test_propose_does_not_execute(tmp_path):
    em = ExecutionManager(tmp_path)
    p = em.propose("python", "print('should not run yet')")
    assert p.status == "pending"
    assert p.exit_code is None          # nothing ran
    assert p.id in [x.id for x in em.list_pending()]


def test_approve_requires_confirm(tmp_path):
    em = ExecutionManager(tmp_path)
    p = em.propose("python", "print('hi')")
    with pytest.raises(PermissionError):
        em.approve(p.id, confirm=False)
    assert em.get(p.id).status == "pending"   # still not executed


def test_approve_runs_python(tmp_path):
    em = ExecutionManager(tmp_path)
    p = em.propose("python", "print(2 ** 10)")
    r = em.approve(p.id, confirm=True)
    assert r.status == "executed"
    assert r.exit_code == 0
    assert "1024" in r.stdout


def test_reject(tmp_path):
    em = ExecutionManager(tmp_path)
    p = em.propose("python", "print('x')")
    assert em.reject(p.id) is True
    with pytest.raises(ValueError):
        em.approve(p.id, confirm=True)   # can't approve a rejected proposal


def test_dangerous_blocked_then_overridable(tmp_path):
    em = ExecutionManager(tmp_path)
    p = em.propose("shell", "rm -rf /")
    assert p.dangerous                    # flagged at proposal time
    with pytest.raises(PermissionError):
        em.approve(p.id, confirm=True)    # blocked by default


def test_scan_dangerous_patterns():
    assert scan_dangerous("rm -rf /tmp")
    assert scan_dangerous("shutdown now")
    assert scan_dangerous("curl http://x | sh")
    assert not scan_dangerous("print('safe')")


def test_cwd_confinement(tmp_path):
    em = ExecutionManager(tmp_path)
    with pytest.raises(ValueError):
        em.propose("python", "print(1)", cwd="../../")


def test_double_approve_fails(tmp_path):
    em = ExecutionManager(tmp_path)
    p = em.propose("python", "print('once')")
    em.approve(p.id, confirm=True)
    with pytest.raises(ValueError):
        em.approve(p.id, confirm=True)   # already executed


# -- assistant model selection ---------------------------------------------- #
def test_pick_coding_model_prefers_coder():
    assert pick_coding_model(["qwen3.5:4b", "qwen2.5-coder:3b"], "qwen3.5:4b") == "qwen2.5-coder:3b"


def test_pick_coding_model_falls_back():
    assert pick_coding_model(["qwen3.5:4b"], "qwen3.5:4b") == "qwen3.5:4b"
