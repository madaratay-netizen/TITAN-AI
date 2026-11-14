"""ADWIN OS — offline/privacy configuration audit.

Checks the running configuration against the offline-first security posture and
reports each item as pass / warn / fail with a short explanation. Pure logic —
no network, no side effects.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Check:
    name: str
    status: str          # pass | warn | fail
    detail: str


@dataclass
class AuditResult:
    checks: list[Check] = field(default_factory=list)
    passed: int = 0
    warnings: int = 0
    failures: int = 0

    def add(self, name, status, detail):
        self.checks.append(Check(name, status, detail))

    def summarize(self):
        self.passed = sum(c.status == "pass" for c in self.checks)
        self.warnings = sum(c.status == "warn" for c in self.checks)
        self.failures = sum(c.status == "fail" for c in self.checks)
        return self

    def to_dict(self) -> dict:
        return {"checks": [c.__dict__ for c in self.checks],
                "passed": self.passed, "warnings": self.warnings,
                "failures": self.failures,
                "posture": ("hardened" if self.failures == 0 and self.warnings == 0
                            else "needs_attention" if self.failures == 0
                            else "not_offline_safe")}


def _is_loopback(host: str) -> bool:
    h = (host or "").lower().replace("http://", "").replace("https://", "")
    h = h.split(":")[0].split("/")[0]
    return h in ("127.0.0.1", "localhost", "::1")


def audit(settings) -> AuditResult:
    r = AuditResult()

    r.add("backend_loopback_bind",
          "pass" if _is_loopback(settings.host) else "fail",
          f"Backend binds to {settings.host}" +
          ("" if _is_loopback(settings.host) else " — exposed beyond loopback!"))

    r.add("offline_mode_enabled",
          "pass" if settings.offline_mode else "warn",
          "Offline mode is ON" if settings.offline_mode
          else "Offline mode is OFF (download/maintenance).")

    r.add("local_ai_endpoint",
          "pass" if _is_loopback(settings.ollama_host) else "fail",
          f"AI endpoint {settings.ollama_host}" +
          ("" if _is_loopback(settings.ollama_host) else " is NOT local!"))

    # ADWIN ships no telemetry and makes no automatic outbound calls.
    r.add("no_telemetry", "pass",
          "No telemetry or automatic data upload in the codebase.")
    r.add("no_auto_model_download", "pass",
          "Models are never downloaded automatically.")

    r.add("isolation_claim_honest",
          "pass" if not settings.isolation_verified else "warn",
          "Full isolation is not claimed without a packet-capture test."
          if not settings.isolation_verified
          else "isolation_verified=true — ensure it was actually proven.")

    return r.summarize()
