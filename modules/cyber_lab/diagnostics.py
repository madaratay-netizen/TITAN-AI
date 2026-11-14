"""ADWIN OS — IT & Cyber Lab diagnostics (defensive/read-only).

System resource monitoring, disk health, network interface analysis, and
IP/DNS diagnostics. All functions are read-only and local; none modify the
system, and none perform scanning or exploitation (see scanner.py for the
authorization-gated port check).
"""
from __future__ import annotations

import platform
import re
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field

try:
    import psutil  # type: ignore
    _HAS_PSUTIL = True
except Exception:  # pragma: no cover
    psutil = None  # type: ignore
    _HAS_PSUTIL = False

GB = 1024 ** 3
# Accept hostnames and IPv4/IPv6 literals; reject anything with shell metachars.
_HOST_RE = re.compile(r"^[A-Za-z0-9._:-]{1,253}$")


def valid_host(host: str) -> bool:
    return bool(host) and bool(_HOST_RE.match(host))


# --------------------------------------------------------------------------- #
def system_health() -> dict:
    out: dict = {"os": platform.system(), "ok": True}
    if _HAS_PSUTIL:
        out["cpu_percent"] = psutil.cpu_percent(interval=0.2)
        vm = psutil.virtual_memory()
        out["memory"] = {"total_gb": round(vm.total / GB, 2),
                         "used_percent": vm.percent,
                         "available_gb": round(vm.available / GB, 2)}
        try:
            out["uptime_sec"] = int(time.time() - psutil.boot_time())
        except Exception:
            out["uptime_sec"] = None
        try:
            la = psutil.getloadavg()
            out["load_avg"] = [round(x, 2) for x in la]
        except (AttributeError, OSError):
            out["load_avg"] = None
        out["process_count"] = len(psutil.pids())
    else:
        out["note"] = "psutil not installed; limited metrics"
    return out


def disk_health() -> dict:
    disks = []
    if _HAS_PSUTIL:
        for part in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue
            warn = u.percent >= 90
            disks.append({
                "mount": part.mountpoint, "fs": part.fstype,
                "total_gb": round(u.total / GB, 2),
                "free_gb": round(u.free / GB, 2),
                "used_percent": u.percent,
                "status": "LOW SPACE" if warn else "ok"})
    # SMART / hardware status where available.
    smart = _smart_status()
    return {"partitions": disks, "smart": smart}


def _smart_status() -> dict:
    system = platform.system()
    if system == "Windows":
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_DiskDrive | "
                 "Select-Object Model,Status | ConvertTo-Json"],
                capture_output=True, text=True, timeout=8, check=False)
            import json
            data = json.loads(out.stdout or "[]")
            if isinstance(data, dict):
                data = [data]
            return {"source": "wmi", "drives": data}
        except Exception as exc:
            return {"source": "wmi", "error": str(exc)}
    if shutil.which("smartctl"):
        return {"source": "smartctl", "note": "run 'smartctl -H <dev>' per device"}
    return {"source": "none", "note": "no SMART tool available"}


def net_interfaces() -> dict:
    ifaces = []
    if _HAS_PSUTIL:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        for name, addr_list in addrs.items():
            entry = {"name": name, "addresses": [], "up": None, "speed_mbps": None}
            st = stats.get(name)
            if st:
                entry["up"] = st.isup
                entry["speed_mbps"] = st.speed
            for a in addr_list:
                fam = getattr(a.family, "name", str(a.family))
                if "AF_INET" in fam or "AF_PACKET" in fam or "AF_LINK" in fam:
                    entry["addresses"].append({"family": fam, "address": a.address})
            ifaces.append(entry)
    else:
        ifaces.append({"name": "unknown", "note": "psutil not installed"})
    return {"hostname": socket.gethostname(), "interfaces": ifaces}


def dns_lookup(host: str) -> dict:
    if not valid_host(host):
        raise ValueError("invalid host")
    result: dict = {"host": host, "addresses": []}
    try:
        infos = socket.getaddrinfo(host, None)
        seen = set()
        for family, _, _, _, sockaddr in infos:
            ip = sockaddr[0]
            if ip not in seen:
                seen.add(ip)
                result["addresses"].append({
                    "ip": ip,
                    "family": "IPv6" if family == socket.AF_INET6 else "IPv4"})
        result["resolved"] = True
    except socket.gaierror as exc:
        result["resolved"] = False
        result["error"] = str(exc)
    return result


def ping(host: str, count: int = 4, timeout: int = 10) -> dict:
    """Run the system ping (args are a list — no shell, no injection)."""
    if not valid_host(host):
        raise ValueError("invalid host")
    count = max(1, min(count, 10))
    if platform.system() == "Windows":
        argv = ["ping", "-n", str(count), host]
    else:
        argv = ["ping", "-c", str(count), host]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"host": host, "ok": False, "error": "ping timed out"}
    except OSError as exc:
        return {"host": host, "ok": False, "error": f"ping unavailable: {exc}"}
    text = proc.stdout or ""
    # Extract an average RTT if present (best-effort, platform-agnostic).
    m = re.search(r"(?:Average|avg)[^\d]*([\d.]+)\s*ms", text, re.I) or \
        re.search(r"=\s*[\d.]+/([\d.]+)/", text)
    return {"host": host, "ok": proc.returncode == 0,
            "avg_ms": float(m.group(1)) if m else None,
            "output": text[-1500:]}
