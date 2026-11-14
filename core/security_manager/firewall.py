"""TITAN AI — firewall rule generator (offline hardening).

Generates reviewed firewall rulesets for the two network modes. TITAN NEVER
applies these automatically (that would modify system security settings) — it
writes them for an operator to review and apply with the appropriate privileges.

Modes:
  offline  — default-drop outbound; allow loopback + established only.
  download — additionally allow DNS + HTTP/HTTPS outbound (for models/updates).
"""
from __future__ import annotations

from pathlib import Path

MODES = ("offline", "download")


def nftables_ruleset(mode: str) -> str:
    if mode not in MODES:
        raise ValueError("mode must be 'offline' or 'download'")
    if mode == "offline":
        out_rules = (
            "        ct state established,related accept\n"
            "        oif \"lo\" accept\n"
            "        # Strict offline: no other outbound allowed.\n"
            "        counter drop\n")
        comment = "TITAN AI — STRICT OFFLINE (no outbound except loopback)"
    else:
        out_rules = (
            "        ct state established,related accept\n"
            "        oif \"lo\" accept\n"
            "        # Download mode: DNS + HTTP/HTTPS only, logged.\n"
            "        udp dport 53 accept\n"
            "        tcp dport 53 accept\n"
            "        tcp dport { 80, 443 } accept\n"
            "        counter log prefix \"titan-egress-drop \" drop\n")
        comment = "TITAN AI — DOWNLOAD MODE (DNS + HTTP/HTTPS outbound)"
    return (
        f"#!/usr/sbin/nft -f\n# {comment}\n"
        "flush ruleset\n\n"
        "table inet titan {\n"
        "    chain input {\n"
        "        type filter hook input priority 0; policy drop;\n"
        "        ct state established,related accept\n"
        "        iif \"lo\" accept\n"
        "        # TITAN services bind to loopback only; no inbound needed.\n"
        "    }\n"
        "    chain forward {\n"
        "        type filter hook forward priority 0; policy drop;\n"
        "    }\n"
        "    chain output {\n"
        "        type filter hook output priority 0; policy drop;\n"
        f"{out_rules}"
        "    }\n"
        "}\n")


def windows_ps1(mode: str, app_dir: str = r"C:\TITAN-AI") -> str:
    """A PowerShell script the user runs (as admin) to block TITAN outbound.

    This blocks outbound for the TITAN app directory only; it does not alter
    global firewall policy. Download mode removes the block.
    """
    if mode not in MODES:
        raise ValueError("mode must be 'offline' or 'download'")
    if mode == "offline":
        return (
            "# TITAN AI — block outbound for the app (run as Administrator).\n"
            "# Blocks only TITAN's own executables, not the whole system.\n"
            f"$app = '{app_dir}'\n"
            "Get-ChildItem -Path $app -Recurse -Include *.exe | ForEach-Object {\n"
            "  New-NetFirewallRule -DisplayName \"TITAN-block-$($_.Name)\" "
            "-Direction Outbound -Program $_.FullName -Action Block "
            "-Profile Any -ErrorAction SilentlyContinue | Out-Null\n"
            "}\n"
            "Write-Output 'TITAN outbound blocked. Remove with the download-mode script.'\n")
    return (
        "# TITAN AI — remove TITAN outbound block (run as Administrator).\n"
        "Get-NetFirewallRule -DisplayName 'TITAN-block-*' -ErrorAction "
        "SilentlyContinue | Remove-NetFirewallRule\n"
        "Write-Output 'TITAN outbound block removed (download mode).'\n")


def write_templates(out_dir: str | Path) -> list[str]:
    """Write all rule templates to infrastructure/firewall/. Returns paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for mode in MODES:
        nft = out / f"nftables.{mode}.nft"
        nft.write_text(nftables_ruleset(mode), encoding="utf-8")
        ps = out / f"windows_firewall.{mode}.ps1"
        ps.write_text(windows_ps1(mode), encoding="utf-8")
        written += [str(nft), str(ps)]
    readme = out / "README.md"
    readme.write_text(
        "# TITAN AI firewall rules (reviewed templates)\n\n"
        "TITAN generates these; it never applies them automatically.\n\n"
        "- `nftables.offline.nft` / `nftables.download.nft` — Linux (SSD target):\n"
        "  `sudo nft -f nftables.offline.nft`\n"
        "- `windows_firewall.offline.ps1` / `.download.ps1` — Windows dev host,\n"
        "  run as Administrator. Blocks only TITAN's own executables.\n\n"
        "Offline mode: loopback + established only. Download mode: + DNS/HTTP(S).\n",
        encoding="utf-8")
    written.append(str(readme))
    return written
