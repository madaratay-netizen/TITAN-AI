"""ADWIN OS — partition planner (safe, read-only logic).

Computes a concrete partition plan from a disk's *actual* capacity and judges
whether a device is a safe target. This module performs NO disk operations — it
only produces the plan and the safety verdict that the confirmation-gated shell
script displays before asking the operator to approve.

Labels: ADWIN_EFI, ADWIN_BOOT, ADWIN_SYSTEM, ADWIN_MODELS, ADWIN_WORKSPACE.
"""
from __future__ import annotations

from dataclasses import dataclass, field

GIB = 1024 ** 3

# Preferred fixed sizes (GiB) for the non-workspace partitions.
ESP_GIB = 1
BOOT_GIB = 21
SYSTEM_GIB = 14
MODELS_GIB = 23
MIN_WORKSPACE_GIB = 10
RESERVE_MIN_GIB = 2.0
RESERVE_FRACTION = 0.05

# Expected external-SSD size window (GiB) for a "128 GB" device.
EXPECTED_MIN_GIB = 100
EXPECTED_MAX_GIB = 140


@dataclass
class Partition:
    num: int
    label: str
    fs: str
    size_gib: float
    mount: str
    windows_visible: bool
    purpose: str

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class PartitionPlan:
    device_total_gib: float
    usable_gib: float
    reserve_gib: float
    partitions: list[Partition] = field(default_factory=list)
    scaled: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"device_total_gib": round(self.device_total_gib, 2),
                "usable_gib": round(self.usable_gib, 2),
                "reserve_gib": round(self.reserve_gib, 2),
                "scaled": self.scaled,
                "partitions": [p.to_dict() for p in self.partitions],
                "notes": self.notes}


def compute_plan(total_bytes: int) -> PartitionPlan:
    """Compute the partition plan for a disk of `total_bytes`.

    Fixed EFI/BOOT/SYSTEM/MODELS where they fit; WORKSPACE takes the rest minus a
    reserve. On a smaller disk the fixed partitions scale down proportionally so a
    minimum workspace + reserve always fit. Raises if the disk is too small.
    """
    total_gib = total_bytes / GIB
    # Leave ~0.5% for GPT/alignment overhead.
    usable = total_gib * 0.995
    reserve = max(RESERVE_MIN_GIB, usable * RESERVE_FRACTION)

    esp, boot, system, models = ESP_GIB, BOOT_GIB, SYSTEM_GIB, MODELS_GIB
    fixed = esp + boot + system + models
    scaled = False
    notes: list[str] = []

    if fixed + MIN_WORKSPACE_GIB + reserve > usable:
        # Scale the scalable partitions (boot/system/models) to fit.
        scaled = True
        avail_for_scalable = usable - esp - MIN_WORKSPACE_GIB - reserve
        scalable = boot + system + models
        if avail_for_scalable < scalable * 0.4:
            raise ValueError(
                f"disk too small: {usable:.1f} GiB usable cannot hold a ADWIN "
                f"layout (need >= {esp + scalable * 0.4 + MIN_WORKSPACE_GIB + reserve:.1f} GiB)")
        factor = max(0.4, avail_for_scalable / scalable)
        boot, system, models = boot * factor, system * factor, models * factor
        notes.append(f"Small disk: boot/system/models scaled to {factor*100:.0f}%.")

    workspace = usable - (esp + boot + system + models) - reserve
    workspace = max(MIN_WORKSPACE_GIB, workspace)

    def r(x):  # round to 1 decimal
        return round(x, 1)

    parts = [
        Partition(1, "ADWIN_EFI", "FAT32", r(esp), "/boot/efi", True, "UEFI boot (ESP), GRUB on the SSD only"),
        Partition(2, "ADWIN_BOOT", "ext4", r(boot), "/run/live/medium", False, "Live base (read-only SquashFS) + boot files"),
        Partition(3, "ADWIN_SYSTEM", "ext4", r(system), "/opt/adwin", False, "Persistent app/runtime, deps, config, logs + overlay"),
        Partition(4, "ADWIN_MODELS", "ext4", r(models), "/opt/adwin/models", False, "Optional AI model weights"),
        Partition(5, "ADWIN_WORKSPACE", "exFAT", r(workspace), "/workspace", True, "User outputs — cross-OS, protected"),
    ]
    return PartitionPlan(device_total_gib=total_gib, usable_gib=usable,
                         reserve_gib=reserve, partitions=parts, scaled=scaled, notes=notes)


@dataclass
class TargetVerdict:
    safe: bool
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__


def classify_target(size_bytes: int, bus: str = "", is_system_disk: bool = False,
                    model: str = "") -> TargetVerdict:
    """Judge whether a device is a safe partition target. Never trusts serial
    (some USB enclosures report all-zeros)."""
    v = TargetVerdict(safe=True)
    if is_system_disk:
        v.safe = False
        v.reasons.append("This is the running system disk — refused.")
    if (bus or "").lower() not in ("usb", "usbstorage"):
        v.safe = False
        v.reasons.append(f"Device bus is '{bus or 'unknown'}', not USB — refused "
                         "(the ADWIN SSD is an external USB device).")
    size_gib = size_bytes / GIB
    if not (EXPECTED_MIN_GIB <= size_gib <= EXPECTED_MAX_GIB):
        v.warnings.append(
            f"Size {size_gib:.1f} GiB is outside the expected 128 GB window "
            f"({EXPECTED_MIN_GIB}-{EXPECTED_MAX_GIB} GiB) — double-check this is the right disk.")
    v.warnings.append("Identify by MODEL + SIZE + BUS; this enclosure's serial may "
                      "be unreliable (all-zeros).")
    return v


def render_plan_table(plan: PartitionPlan) -> str:
    lines = [f"Device: {plan.device_total_gib:.2f} GiB total, "
             f"{plan.usable_gib:.2f} GiB usable, reserve {plan.reserve_gib:.1f} GiB",
             f"{'#':<2} {'LABEL':<16} {'FS':<6} {'SIZE':>8}  MOUNT"]
    for p in plan.partitions:
        lines.append(f"{p.num:<2} {p.label:<16} {p.fs:<6} {p.size_gib:>6.1f}G  {p.mount}")
    for n in plan.notes:
        lines.append(f"note: {n}")
    return "\n".join(lines)
