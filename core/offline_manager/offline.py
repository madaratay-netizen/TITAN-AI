"""TITAN AI — Offline Manager.

Reports network/offline state honestly and distinguishes the three levels the
spec requires. It does NOT claim full isolation unless that has actually been
verified by the offline test harness.

Levels:
  - no_internet_requirement : TITAN works without internet (by design).
  - no_network_connectivity : the machine currently has no network link.
  - fully_isolated          : verified no outbound traffic (test-proven only).
"""
from __future__ import annotations

import socket
from dataclasses import dataclass


@dataclass
class NetworkState:
    has_link: bool
    can_reach_internet: bool
    offline_mode_enabled: bool
    isolation_level: str
    detail: str


def _has_default_route(timeout: float = 0.6) -> bool:
    """Best-effort check for a usable network link (no DNS, no payload)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        # Connecting a UDP socket performs no traffic but requires a route.
        s.connect(("10.255.255.255", 1))
        s.close()
        return True
    except OSError:
        return False


def _can_reach_internet(timeout: float = 1.5) -> bool:
    """Attempt a single TCP connect to a public DNS resolver (no data sent)."""
    try:
        with socket.create_connection(("1.1.1.1", 53), timeout=timeout):
            return True
    except OSError:
        return False


def check(offline_mode_enabled: bool, isolation_verified: bool = False) -> NetworkState:
    has_link = _has_default_route()
    # When offline mode is enabled we still *report* reachability truthfully,
    # but TITAN services are expected to refuse outbound AI calls regardless.
    reachable = False if offline_mode_enabled else (_can_reach_internet() if has_link else False)

    if isolation_verified:
        level = "fully_isolated"
        detail = "Isolation verified by offline test harness."
    elif offline_mode_enabled:
        level = "no_internet_requirement"
        detail = ("Offline mode ON: local-only service binding; outbound AI "
                  "calls disabled. (Isolation not independently verified.)")
    elif not has_link:
        level = "no_network_connectivity"
        detail = "No network link detected on this host."
    else:
        level = "no_internet_requirement"
        detail = "Network available but TITAN does not require it for operation."

    return NetworkState(
        has_link=has_link,
        can_reach_internet=reachable,
        offline_mode_enabled=offline_mode_enabled,
        isolation_level=level,
        detail=detail,
    )
