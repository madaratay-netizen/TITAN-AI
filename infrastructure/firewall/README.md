# TITAN AI firewall rules (reviewed templates)

TITAN generates these; it never applies them automatically.

- `nftables.offline.nft` / `nftables.download.nft` — Linux (SSD target):
  `sudo nft -f nftables.offline.nft`
- `windows_firewall.offline.ps1` / `.download.ps1` — Windows dev host,
  run as Administrator. Blocks only TITAN's own executables.

Offline mode: loopback + established only. Download mode: + DNS/HTTP(S).
