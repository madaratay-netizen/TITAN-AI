"""ADWIN OS — Hardware Detection

Detects real CPU / RAM / storage / GPU / acceleration-backend facts on the
machine it runs on. Works on Windows (development) and Linux (SSD target).

Design rules (per ADWIN engineering rules):
- Never assume a GPU, VRAM amount, or RAM size. Measure it.
- Never crash the whole system if one probe fails; degrade and record why.
- Use psutil when available for richer data, but keep working without it so
  the engine is testable with zero third-party dependencies.
"""
from __future__ import annotations

import ctypes
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from typing import Optional

try:  # optional, enriches CPU/RAM data
    import psutil  # type: ignore
    _HAS_PSUTIL = True
except Exception:  # pragma: no cover - environment dependent
    psutil = None  # type: ignore
    _HAS_PSUTIL = False

GB = 1024 ** 3
MIB = 1024 ** 2


def _run(cmd: list[str], timeout: int = 8) -> Optional[str]:
    """Run a command, returning stdout or None. Never raises."""
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        if out.returncode == 0:
            return out.stdout
        return out.stdout or None
    except (OSError, subprocess.SubprocessError):
        return None


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass
class CPUInfo:
    model: str = "unknown"
    physical_cores: int = 0
    logical_cores: int = 0
    max_clock_mhz: int = 0
    arch: str = ""


@dataclass
class MemoryInfo:
    total_gb: float = 0.0
    available_gb: float = 0.0


@dataclass
class GPUInfo:
    vendor: str = "unknown"          # nvidia / amd / intel / apple / unknown
    model: str = "unknown"
    vram_total_mb: int = 0
    vram_free_mb: int = 0
    driver: str = ""
    compute_capability: str = ""     # NVIDIA CUDA cc, e.g. "8.6"


@dataclass
class DiskInfo:
    mount: str
    filesystem: str = ""
    total_gb: float = 0.0
    free_gb: float = 0.0
    removable: bool = False


@dataclass
class Accel:
    cuda: bool = False
    vulkan: bool = False
    rocm: bool = False
    metal: bool = False
    backends: list[str] = field(default_factory=list)


@dataclass
class HardwareReport:
    os_name: str = ""
    os_version: str = ""
    arch: str = ""
    is_linux: bool = False
    cpu: CPUInfo = field(default_factory=CPUInfo)
    memory: MemoryInfo = field(default_factory=MemoryInfo)
    gpus: list[GPUInfo] = field(default_factory=list)
    disks: list[DiskInfo] = field(default_factory=list)
    accel: Accel = field(default_factory=Accel)
    probe_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @property
    def best_gpu(self) -> Optional[GPUInfo]:
        """The GPU with the most VRAM (what model-loading decisions use)."""
        if not self.gpus:
            return None
        return max(self.gpus, key=lambda g: g.vram_total_mb)


# --------------------------------------------------------------------------- #
# CPU
# --------------------------------------------------------------------------- #
def _detect_cpu() -> CPUInfo:
    info = CPUInfo(arch=platform.machine())
    info.logical_cores = os.cpu_count() or 0
    info.model = platform.processor() or ""

    if _HAS_PSUTIL:
        try:
            info.physical_cores = psutil.cpu_count(logical=False) or 0
            freq = psutil.cpu_freq()
            if freq:
                info.max_clock_mhz = int(freq.max or freq.current or 0)
        except Exception:
            pass

    system = platform.system()
    if system == "Linux":
        try:
            with open("/proc/cpuinfo", encoding="utf-8") as fh:
                text = fh.read()
            m = re.search(r"model name\s*:\s*(.+)", text)
            if m:
                info.model = m.group(1).strip()
            if not info.physical_cores:
                ids = set(re.findall(r"core id\s*:\s*(\d+)", text))
                info.physical_cores = len(ids) or info.logical_cores
        except OSError:
            pass
    elif system == "Windows" and (not info.model or not info.max_clock_mhz):
        out = _run([
            "powershell", "-NoProfile", "-Command",
            "Get-CimInstance Win32_Processor | "
            "Select-Object -First 1 Name,NumberOfCores,MaxClockSpeed | ConvertTo-Json",
        ])
        if out:
            try:
                data = json.loads(out)
                info.model = (data.get("Name") or info.model).strip()
                info.physical_cores = info.physical_cores or int(data.get("NumberOfCores") or 0)
                info.max_clock_mhz = info.max_clock_mhz or int(data.get("MaxClockSpeed") or 0)
            except (ValueError, json.JSONDecodeError):
                pass

    if not info.physical_cores:
        info.physical_cores = info.logical_cores
    return info


# --------------------------------------------------------------------------- #
# Memory
# --------------------------------------------------------------------------- #
class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _detect_memory() -> MemoryInfo:
    if _HAS_PSUTIL:
        try:
            vm = psutil.virtual_memory()
            return MemoryInfo(round(vm.total / GB, 2), round(vm.available / GB, 2))
        except Exception:
            pass

    system = platform.system()
    if system == "Linux":
        try:
            with open("/proc/meminfo", encoding="utf-8") as fh:
                text = fh.read()
            total = int(re.search(r"MemTotal:\s*(\d+)", text).group(1)) * 1024
            avail_m = re.search(r"MemAvailable:\s*(\d+)", text)
            avail = int(avail_m.group(1)) * 1024 if avail_m else total
            return MemoryInfo(round(total / GB, 2), round(avail / GB, 2))
        except (OSError, AttributeError):
            pass
    elif system == "Windows":
        try:
            stat = _MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return MemoryInfo(
                round(stat.ullTotalPhys / GB, 2),
                round(stat.ullAvailPhys / GB, 2),
            )
        except Exception:
            pass
    return MemoryInfo()


# --------------------------------------------------------------------------- #
# GPU
# --------------------------------------------------------------------------- #
def _detect_nvidia() -> list[GPUInfo]:
    if not shutil.which("nvidia-smi"):
        return []
    out = _run([
        "nvidia-smi",
        "--query-gpu=name,memory.total,memory.free,driver_version,compute_cap",
        "--format=csv,noheader,nounits",
    ])
    if not out:
        return []
    gpus: list[GPUInfo] = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        gpus.append(GPUInfo(
            vendor="nvidia",
            model=parts[0],
            vram_total_mb=int(float(parts[1])) if parts[1].replace(".", "").isdigit() else 0,
            vram_free_mb=int(float(parts[2])) if parts[2].replace(".", "").isdigit() else 0,
            driver=parts[3],
            compute_capability=parts[4] if len(parts) > 4 else "",
        ))
    return gpus


def _detect_gpus_windows() -> list[GPUInfo]:
    """Fallback listing of all adapters (incl. Intel/AMD iGPUs) via WMI."""
    out = _run([
        "powershell", "-NoProfile", "-Command",
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name,AdapterRAM,DriverVersion | ConvertTo-Json",
    ])
    if not out:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    gpus = []
    for d in data:
        name = (d.get("Name") or "unknown").strip()
        vendor = "unknown"
        low = name.lower()
        if "nvidia" in low:
            vendor = "nvidia"
        elif "amd" in low or "radeon" in low:
            vendor = "amd"
        elif "intel" in low:
            vendor = "intel"
        ram = d.get("AdapterRAM") or 0
        gpus.append(GPUInfo(
            vendor=vendor,
            model=name,
            vram_total_mb=int(ram / MIB) if ram else 0,
            driver=(d.get("DriverVersion") or "").strip(),
        ))
    return gpus


def _detect_gpus_linux() -> list[GPUInfo]:
    out = _run(["lspci"])
    if not out:
        return []
    gpus = []
    for line in out.splitlines():
        if re.search(r"VGA compatible controller|3D controller", line, re.I):
            model = line.split(":")[-1].strip()
            low = model.lower()
            vendor = ("nvidia" if "nvidia" in low else
                      "amd" if ("amd" in low or "radeon" in low) else
                      "intel" if "intel" in low else "unknown")
            gpus.append(GPUInfo(vendor=vendor, model=model))
    return gpus


def _detect_gpus() -> list[GPUInfo]:
    nvidia = _detect_nvidia()
    system = platform.system()
    others = _detect_gpus_windows() if system == "Windows" else (
        _detect_gpus_linux() if system == "Linux" else [])

    # Merge: prefer nvidia-smi data for NVIDIA cards (it has real VRAM).
    merged: list[GPUInfo] = list(nvidia)
    nvidia_models = {g.model for g in nvidia}
    for g in others:
        if g.vendor == "nvidia" and any(g.model in nm or nm in g.model for nm in nvidia_models):
            continue  # already covered by nvidia-smi
        merged.append(g)
    return merged


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #
def _detect_disks() -> list[DiskInfo]:
    disks: list[DiskInfo] = []
    if _HAS_PSUTIL:
        try:
            for part in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                except (PermissionError, OSError):
                    continue
                removable = "removable" in (part.opts or "").lower()
                disks.append(DiskInfo(
                    mount=part.mountpoint,
                    filesystem=part.fstype,
                    total_gb=round(usage.total / GB, 2),
                    free_gb=round(usage.free / GB, 2),
                    removable=removable,
                ))
            return disks
        except Exception:
            disks = []

    # Fallback via shutil on known roots.
    if platform.system() == "Windows":
        roots = [f"{d}:\\" for d in "CDEFGHIJ" if os.path.exists(f"{d}:\\")]
    else:
        roots = ["/", "/mnt", "/media", "/home"]
        roots = [r for r in roots if os.path.exists(r)]
    for r in roots:
        try:
            usage = shutil.disk_usage(r)
            disks.append(DiskInfo(
                mount=r,
                total_gb=round(usage.total / GB, 2),
                free_gb=round(usage.free / GB, 2),
            ))
        except OSError:
            continue
    return disks


# --------------------------------------------------------------------------- #
# Acceleration backends
# --------------------------------------------------------------------------- #
def _detect_accel(gpus: list[GPUInfo]) -> Accel:
    accel = Accel()
    if shutil.which("nvidia-smi") and any(g.vendor == "nvidia" for g in gpus):
        accel.cuda = True
        accel.backends.append("cuda")
    if shutil.which("vulkaninfo"):
        accel.vulkan = True
        accel.backends.append("vulkan")
    if shutil.which("rocminfo") or os.path.exists("/opt/rocm"):
        accel.rocm = True
        accel.backends.append("rocm")
    if platform.system() == "Darwin":
        accel.metal = True
        accel.backends.append("metal")
    # CPU is always an available backend (llama.cpp / ggml fallback).
    accel.backends.append("cpu")
    return accel


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def detect() -> HardwareReport:
    report = HardwareReport(
        os_name=platform.system(),
        os_version=platform.version(),
        arch=platform.machine(),
        is_linux=platform.system() == "Linux",
    )
    if not _HAS_PSUTIL:
        report.probe_notes.append("psutil not installed — using built-in fallbacks")

    for label, fn, attr in (
        ("cpu", _detect_cpu, "cpu"),
        ("memory", _detect_memory, "memory"),
    ):
        try:
            setattr(report, attr, fn())
        except Exception as exc:  # pragma: no cover
            report.probe_notes.append(f"{label} probe failed: {exc}")

    try:
        report.gpus = _detect_gpus()
    except Exception as exc:  # pragma: no cover
        report.probe_notes.append(f"gpu probe failed: {exc}")
    if not report.gpus:
        report.probe_notes.append("no GPU detected — CPU-only inference")

    try:
        report.disks = _detect_disks()
    except Exception as exc:  # pragma: no cover
        report.probe_notes.append(f"disk probe failed: {exc}")

    try:
        report.accel = _detect_accel(report.gpus)
    except Exception as exc:  # pragma: no cover
        report.probe_notes.append(f"accel probe failed: {exc}")

    return report


if __name__ == "__main__":
    print(detect().to_json())
