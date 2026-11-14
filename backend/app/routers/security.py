"""ADWIN OS — Security / offline-hardening API routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core.security_manager import egress, audit, firewall
from core.offline_manager import offline
from backend.app.config import settings

router = APIRouter(prefix="/api/security", tags=["security"])


@router.get("/audit")
def config_audit():
    return audit.audit(settings).to_dict()


@router.get("/status")
def status():
    a = audit.audit(settings).to_dict()
    net = offline.check(settings.offline_mode, settings.isolation_verified)
    return {"offline": net.__dict__, "audit": {"posture": a["posture"],
            "passed": a["passed"], "warnings": a["warnings"], "failures": a["failures"]}}


@router.post("/egress-test")
def egress_test():
    return egress.egress_check().to_dict()


@router.get("/firewall")
def firewall_rules(mode: str = "offline"):
    try:
        return {"mode": mode,
                "nftables": firewall.nftables_ruleset(mode),
                "windows_ps1": firewall.windows_ps1(mode),
                "note": "Reviewed templates. ADWIN never applies these automatically."}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
