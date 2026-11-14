"""ADWIN OS — Developer Lab execution manager (SECURITY-CRITICAL).

Enforces the spec's hard rule: generated code/commands are NEVER executed
automatically. The flow is always:

    propose()  ->  a Proposal is created, status PENDING, nothing runs
    (the exact command/code is shown to the user)
    approve(id, confirm)  ->  runs it, confined + timed + captured
    reject(id)  ->  discards it

Confinement:
- Execution cwd is forced inside the Developer Lab workspace root.
- A timeout and output cap are always applied.
- Commands matching destructive patterns are blocked unless explicitly allowed.
- Shell commands are NOT auto-elevated and run without a login shell profile.

Note on sandboxing: this provides approval-gating, workspace confinement, a
timeout, and destructive-pattern screening. It is NOT a kernel sandbox. On the
Linux SSD target, wrap execution with bubblewrap/firejail for stronger isolation
(documented in docs/ARCHITECTURE.md).
"""
from __future__ import annotations

import re
import shlex
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

PROPOSAL_TTL_SEC = 600          # pending proposals expire after 10 minutes
DEFAULT_TIMEOUT = 30
MAX_OUTPUT_CHARS = 20000

# Patterns that are destructive / out-of-scope and blocked by default.
DANGEROUS = [
    re.compile(r"\brm\s+-[rf]", re.I),
    re.compile(r"\brmdir\b", re.I),
    re.compile(r"\bdel\b", re.I),
    re.compile(r"\bformat\b", re.I),
    re.compile(r"\bmkfs\b", re.I),
    re.compile(r"\bdd\b\s+if=", re.I),
    re.compile(r"\bshutdown\b|\breboot\b", re.I),
    re.compile(r":\(\)\s*\{.*\};:", re.I),            # fork bomb
    re.compile(r"\bcurl\b.*\|\s*(ba)?sh", re.I),      # pipe-to-shell
    re.compile(r"\bInvoke-Expression\b|\biex\b", re.I),
    re.compile(r">\s*/dev/sd|>\s*\\\\\.\\PhysicalDrive", re.I),
]


def scan_dangerous(text: str) -> list[str]:
    return [p.pattern for p in DANGEROUS if p.search(text)]


@dataclass
class Proposal:
    id: str
    kind: str                     # "shell" | "python"
    content: str
    cwd: str
    created_at: float
    status: str = "pending"       # pending | executed | rejected | expired
    dangerous: list[str] = field(default_factory=list)
    # result (filled after approval)
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    duration_s: float = 0.0

    def expired(self) -> bool:
        return self.status == "pending" and (time.time() - self.created_at) > PROPOSAL_TTL_SEC

    def to_dict(self) -> dict:
        return asdict(self)


class ExecutionManager:
    def __init__(self, workspace_root: str | Path):
        self.root = Path(workspace_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._proposals: dict[str, Proposal] = {}

    def _confine_cwd(self, cwd: Optional[str]) -> Path:
        if not cwd:
            return self.root
        target = (self.root / cwd.lstrip("/\\")).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError("cwd escapes workspace")
        target.mkdir(parents=True, exist_ok=True)
        return target

    def propose(self, kind: str, content: str, cwd: Optional[str] = None) -> Proposal:
        if kind not in ("shell", "python"):
            raise ValueError("kind must be 'shell' or 'python'")
        if not content.strip():
            raise ValueError("empty content")
        self._confine_cwd(cwd)  # validate confinement up front
        p = Proposal(
            id=uuid.uuid4().hex[:12],
            kind=kind, content=content, cwd=cwd or ".",
            created_at=time.time(),
            dangerous=scan_dangerous(content),
        )
        self._proposals[p.id] = p
        return p

    def get(self, pid: str) -> Optional[Proposal]:
        p = self._proposals.get(pid)
        if p and p.expired():
            p.status = "expired"
        return p

    def list_pending(self) -> list[Proposal]:
        out = []
        for p in self._proposals.values():
            if p.expired():
                p.status = "expired"
            if p.status == "pending":
                out.append(p)
        return out

    def reject(self, pid: str) -> bool:
        p = self._proposals.get(pid)
        if not p or p.status != "pending":
            return False
        p.status = "rejected"
        return True

    def approve(self, pid: str, confirm: bool, allow_dangerous: bool = False,
                timeout: int = DEFAULT_TIMEOUT) -> Proposal:
        """Execute a proposal ONLY on explicit confirm=True."""
        p = self._proposals.get(pid)
        if not p:
            raise KeyError("no such proposal")
        if p.status != "pending":
            raise ValueError(f"proposal is '{p.status}', not pending")
        if p.expired():
            p.status = "expired"
            raise ValueError("proposal expired")
        if not confirm:
            raise PermissionError("execution requires explicit confirm=True")
        if p.dangerous and not allow_dangerous:
            raise PermissionError(
                f"blocked: destructive pattern(s) {p.dangerous}; "
                f"re-approve with allow_dangerous=True to override")

        cwd = self._confine_cwd(None if p.cwd == "." else p.cwd)
        if p.kind == "python":
            # Isolated interpreter: ignores env/user site, no implicit cwd on path.
            argv = [sys.executable, "-I", "-c", p.content]
            shell = False
        else:
            argv = p.content
            shell = True  # the user explicitly approved this exact command string

        t0 = time.time()
        try:
            proc = subprocess.run(
                argv, shell=shell, cwd=str(cwd), capture_output=True,
                text=True, timeout=timeout)
            p.exit_code = proc.returncode
            p.stdout = (proc.stdout or "")[:MAX_OUTPUT_CHARS]
            p.stderr = (proc.stderr or "")[:MAX_OUTPUT_CHARS]
        except subprocess.TimeoutExpired:
            p.exit_code = -1
            p.stderr = f"timed out after {timeout}s"
        except Exception as exc:
            p.exit_code = -1
            p.stderr = f"execution error: {exc}"
        p.duration_s = round(time.time() - t0, 3)
        p.status = "executed"
        return p
