"""ADWIN OS — IT & Cyber Lab port checker (authorized, defensive only).

A plain TCP *connect* check against a single host, for verifying which local/
authorized services are listening. This is deliberately NOT an offensive tool:

- No stealth/SYN/raw-socket scanning — only ordinary TCP connects.
- No OS fingerprinting, no service exploitation, no credential testing.
- Single host only; port count is capped.
- Authorization gate: loopback is always allowed; any other target requires an
  explicit `authorized=True` acknowledgement that the caller owns or is
  permitted to test it. Public targets are refused without that acknowledgement.

This matches the spec: "Only enable network scanning against systems the user
owns or is authorized to test."
"""
from __future__ import annotations

import ipaddress
import socket
import time
from dataclasses import dataclass

from modules.cyber_lab.diagnostics import valid_host

MAX_PORTS = 200
CONNECT_TIMEOUT = 0.6

COMMON_PORTS: dict[int, str] = {
    21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp", 53: "dns", 80: "http",
    110: "pop3", 139: "netbios", 143: "imap", 443: "https", 445: "smb",
    465: "smtps", 587: "submission", 631: "ipp", 993: "imaps", 995: "pop3s",
    1433: "mssql", 3306: "mysql", 3389: "rdp", 5432: "postgres", 5900: "vnc",
    6379: "redis", 8000: "http-alt", 8077: "adwin-api", 8080: "http-proxy",
    8443: "https-alt", 9000: "http-alt", 11434: "ollama",
}


@dataclass
class TargetInfo:
    host: str
    ip: str
    scope: str          # loopback | private | public | unresolved


def classify_target(host: str) -> TargetInfo:
    if not valid_host(host):
        raise ValueError("invalid host")
    try:
        ip = socket.gethostbyname(host)
    except socket.gaierror:
        return TargetInfo(host=host, ip="", scope="unresolved")
    addr = ipaddress.ip_address(ip)
    if addr.is_loopback:
        scope = "loopback"
    elif addr.is_private or addr.is_link_local:
        scope = "private"
    else:
        scope = "public"
    return TargetInfo(host=host, ip=ip, scope=scope)


def authorization_required(target: TargetInfo) -> bool:
    """Loopback needs no acknowledgement; everything else does."""
    return target.scope != "loopback"


def scan(host: str, ports: list[int] | None = None,
         authorized: bool = False) -> dict:
    """TCP-connect check `host` on `ports` (default: common ports).

    Returns open ports with service hints, or an authorization error. Never
    raises on a closed/filtered port — those are simply reported as not open.
    """
    target = classify_target(host)
    if target.scope == "unresolved":
        return {"error": f"could not resolve host: {host}", "target": target.__dict__}

    if authorization_required(target) and not authorized:
        return {
            "authorization_required": True,
            "target": target.__dict__,
            "message": (f"Target {target.ip} is {target.scope}. Scanning is only "
                        "permitted on systems you own or are authorized to test. "
                        "Re-submit with authorized=true to confirm authorization."),
        }

    if ports:
        ports = sorted({p for p in ports if 1 <= p <= 65535})[:MAX_PORTS]
    else:
        ports = sorted(COMMON_PORTS)

    open_ports = []
    t0 = time.time()
    for port in ports:
        try:
            with socket.create_connection((target.ip, port), timeout=CONNECT_TIMEOUT):
                open_ports.append({"port": port,
                                   "service": COMMON_PORTS.get(port, "unknown")})
        except (ConnectionRefusedError, socket.timeout, OSError):
            continue
    return {
        "target": target.__dict__,
        "authorized": True,
        "ports_checked": len(ports),
        "open_ports": open_ports,
        "duration_s": round(time.time() - t0, 2),
        "method": "tcp-connect (non-stealth, defensive)",
    }
