"""Security manager tests — firewall generation, config audit, egress shape."""
from dataclasses import dataclass

import pytest

from core.security_manager import firewall, audit, egress


# -- firewall --------------------------------------------------------------- #
def test_nftables_offline_is_default_drop():
    rules = firewall.nftables_ruleset("offline")
    assert "policy drop" in rules
    assert "oif \"lo\" accept" in rules
    # Offline must NOT open 80/443.
    assert "dport { 80, 443 }" not in rules


def test_nftables_download_allows_https():
    rules = firewall.nftables_ruleset("download")
    assert "dport { 80, 443 } accept" in rules
    assert "dport 53 accept" in rules


def test_invalid_mode_rejected():
    with pytest.raises(ValueError):
        firewall.nftables_ruleset("wideopen")


def test_windows_offline_blocks_outbound():
    ps = firewall.windows_ps1("offline")
    assert "Outbound" in ps and "Block" in ps


def test_write_templates(tmp_path):
    files = firewall.write_templates(tmp_path)
    assert any(f.endswith("nftables.offline.nft") for f in files)
    assert (tmp_path / "README.md").exists()


# -- config audit ----------------------------------------------------------- #
@dataclass
class FakeSettings:
    host: str = "127.0.0.1"
    offline_mode: bool = True
    ollama_host: str = "http://127.0.0.1:11434"
    isolation_verified: bool = False


def test_audit_hardened():
    a = audit.audit(FakeSettings()).to_dict()
    assert a["failures"] == 0
    assert a["posture"] in ("hardened", "needs_attention")


def test_audit_flags_exposed_bind():
    a = audit.audit(FakeSettings(host="0.0.0.0")).to_dict()
    assert a["failures"] >= 1
    assert a["posture"] == "not_offline_safe"


def test_audit_flags_remote_ai_endpoint():
    a = audit.audit(FakeSettings(ollama_host="http://example.com:11434")).to_dict()
    names = {c["name"]: c["status"] for c in a["checks"]}
    assert names["local_ai_endpoint"] == "fail"


def test_audit_offline_off_is_warn_not_fail():
    a = audit.audit(FakeSettings(offline_mode=False)).to_dict()
    names = {c["name"]: c["status"] for c in a["checks"]}
    assert names["offline_mode_enabled"] == "warn"


# -- egress (shape; no network assertion) ----------------------------------- #
def test_egress_result_shape():
    # Point at an unreachable local port so the test never depends on the
    # internet; it must classify as blocked.
    r = egress.egress_check(targets=[("127.0.0.1", 1)], timeout=0.5)
    assert r.isolation in ("egress_blocked", "egress_open")
    assert "127.0.0.1:1" in (r.blocked + r.reachable)
