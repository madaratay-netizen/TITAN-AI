"""TITAN AI — egress self-test.

Actively checks whether outbound network access is possible, so the system can
report its true isolation state. It performs only bare TCP connects to public
IP literals (no DNS lookups, no payload, no user data) — the point is to detect
whether egress is open or blocked, e.g. after applying the offline firewall.
"""
from __future__ import annotations

import socket
from dataclasses import dataclass, field

# Public anycast DNS resolvers (IP literals — no DNS, no data sent on connect).
DEFAULT_TARGETS = [("1.1.1.1", 53), ("8.8.8.8", 53), ("9.9.9.9", 53)]


@dataclass
class EgressResult:
    reachable: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    isolation: str = ""          # egress_blocked | egress_open
    detail: str = ""

    def to_dict(self) -> dict:
        return self.__dict__


def _can_connect(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def egress_check(targets=None, timeout: float = 1.5) -> EgressResult:
    targets = targets or DEFAULT_TARGETS
    res = EgressResult()
    for host, port in targets:
        if _can_connect(host, port, timeout):
            res.reachable.append(f"{host}:{port}")
        else:
            res.blocked.append(f"{host}:{port}")
    if res.reachable:
        res.isolation = "egress_open"
        res.detail = (f"Outbound reachable ({len(res.reachable)}/{len(targets)}). "
                      "Not isolated — apply the offline firewall to block egress.")
    else:
        res.isolation = "egress_blocked"
        res.detail = ("No outbound reachability to the tested resolvers. Consistent "
                      "with an isolated/offline network (verify with a full packet "
                      "capture before claiming total isolation).")
    return res
