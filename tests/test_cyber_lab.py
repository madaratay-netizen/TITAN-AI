"""IT & Cyber Lab tests — diagnostics, the authorization gate, log analysis."""
import socket

import pytest

from modules.cyber_lab import diagnostics, scanner, logs


# -- diagnostics ------------------------------------------------------------ #
def test_valid_host():
    assert diagnostics.valid_host("localhost")
    assert diagnostics.valid_host("192.168.1.1")
    assert not diagnostics.valid_host("bad host;rm -rf")
    assert not diagnostics.valid_host("")


def test_dns_localhost_resolves():
    r = diagnostics.dns_lookup("localhost")
    assert r["resolved"] is True
    assert any(a["ip"] in ("127.0.0.1", "::1") for a in r["addresses"])


def test_dns_invalid_host_rejected():
    with pytest.raises(ValueError):
        diagnostics.dns_lookup("evil;rm")


def test_system_health_shape():
    h = diagnostics.system_health()
    assert "os" in h and h["ok"] is True


def test_interfaces_has_hostname():
    r = diagnostics.net_interfaces()
    assert r["hostname"]
    assert isinstance(r["interfaces"], list)


# -- scanner: classification + authorization gate --------------------------- #
def test_classify_loopback():
    assert scanner.classify_target("127.0.0.1").scope == "loopback"


def test_classify_private():
    assert scanner.classify_target("192.168.1.1").scope == "private"


def test_classify_public():
    assert scanner.classify_target("1.1.1.1").scope == "public"


def test_authorization_required_rules():
    assert not scanner.authorization_required(scanner.classify_target("127.0.0.1"))
    assert scanner.authorization_required(scanner.classify_target("192.168.1.1"))
    assert scanner.authorization_required(scanner.classify_target("1.1.1.1"))


def test_public_scan_blocked_without_authorization():
    r = scanner.scan("1.1.1.1", ports=[80], authorized=False)
    assert r.get("authorization_required") is True
    assert "open_ports" not in r          # nothing was scanned


def test_loopback_scan_allowed_and_detects_open_port():
    # Open a real listening socket and confirm the scanner finds it.
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        r = scanner.scan("127.0.0.1", ports=[port], authorized=False)
        assert r["authorized"] is True
        assert any(p["port"] == port for p in r["open_ports"])
    finally:
        srv.close()


def test_closed_port_not_reported_open():
    # A high ephemeral port with nothing listening.
    r = scanner.scan("127.0.0.1", ports=[59999], authorized=False)
    assert r["open_ports"] == []


# -- log analysis ----------------------------------------------------------- #
LOG = """2024-01-01 10:00:00 INFO starting up
2024-01-01 10:00:01 ERROR failed to open /var/data/1
2024-01-01 10:00:02 WARNING low memory
2024-01-01 10:00:03 ERROR failed to open /var/data/2
2024-01-01 10:00:04 CRITICAL disk offline
"""


def test_analyze_text_counts():
    r = logs.analyze_text(LOG)
    assert r["error_count"] == 3          # 2 ERROR + 1 CRITICAL
    assert r["by_level"]["ERROR"] == 2
    assert r["by_level"]["CRITICAL"] == 1
    assert r["by_level"]["WARNING"] == 1


def test_analyze_text_groups_signatures():
    r = logs.analyze_text(LOG)
    # The two "failed to open <path>" lines normalize to one signature.
    sigs = {s["signature"]: s["count"] for s in r["top_error_signatures"]}
    assert any(c == 2 for c in sigs.values())


def test_analyze_file_confinement(tmp_path):
    (tmp_path / "app.log").write_text(LOG, encoding="utf-8")
    r = logs.analyze_file("app.log", allowed_root=tmp_path)
    assert r["error_count"] == 3
    with pytest.raises(ValueError):
        logs.analyze_file("../../etc/passwd", allowed_root=tmp_path)
