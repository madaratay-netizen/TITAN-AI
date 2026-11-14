#!/usr/bin/env python3
"""ADWIN OS — system report CLI.

Runs the full Adaptive Intelligence Engine against the current machine and
prints a human-readable report (add --json for machine output). Uses only the
Python standard library, so it runs with zero installs.

    python scripts/adwin_report.py
    python scripts/adwin_report.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the repo importable when run directly.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.hardware_detection import detector          # noqa: E402
from core.adaptive_engine import engine                # noqa: E402
from core.model_registry.registry import ModelRegistry  # noqa: E402
from core.offline_manager import offline                # noqa: E402
from modules.chat import ollama_client                  # noqa: E402

BAR = "─" * 68


def human(report, result, models, oll, net) -> str:
    g = report.best_gpu
    lines = [
        "", "ADWIN OS — SYSTEM REPORT", BAR,
        f"OS        : {report.os_name} ({report.arch})",
        f"CPU       : {report.cpu.model.strip()}  "
        f"[{report.cpu.physical_cores}C/{report.cpu.logical_cores}T "
        f"@ {report.cpu.max_clock_mhz} MHz]",
        f"RAM       : {report.memory.total_gb} GB total, "
        f"{report.memory.available_gb} GB available",
        f"GPU       : {g.model + ' (' + str(g.vram_total_mb) + ' MB VRAM, cc ' + g.compute_capability + ')' if g else 'none — CPU only'}",
        f"Accel     : {', '.join(report.accel.backends)}",
        "",
        f"PROFILE   : {result.profile.key} — {result.profile.name}",
        f"            {result.profile.summary}",
        f"Budgets   : RAM {result.ram_budget_gb} GB safe, "
        f"VRAM {result.vram_budget_mb} MB safe",
        f"Features  : {', '.join(result.enabled_features)}",
        "",
        f"Ollama    : {'running v' + oll.version if oll.running else 'NOT running'}"
        f"{'  models: ' + ', '.join(oll.models) if oll.models else ''}",
        f"Offline   : {net.isolation_level} — {net.detail}",
        "", "MODEL COMPATIBILITY", BAR,
        f"{'MODEL':<22}{'KIND':<10}{'DL(GB)':>7}  {'STATUS':<12}{'INSTALLED'}",
    ]
    for m in models:
        lines.append(
            f"{m.name:<22}{m.kind:<10}{m.download_gb:>7.1f}  "
            f"{m.compatibility_status:<12}{'yes' if m.installed else '-'}"
        )
    lines += ["", "DISKS", BAR]
    for d in report.disks:
        lines.append(
            f"{d.mount:<10} {d.filesystem:<6} {d.total_gb:>8.1f} GB total, "
            f"{d.free_gb:>8.1f} GB free"
            + ("  [removable]" if d.removable else "")
        )
    if report.probe_notes:
        lines += ["", "NOTES", BAR] + [f"- {n}" for n in report.probe_notes]
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="ADWIN OS system report")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--offline", action="store_true", default=True,
                    help="treat offline mode as enabled (default)")
    args = ap.parse_args()

    report = detector.detect()
    result = engine.evaluate(report)
    registry = ModelRegistry()
    oll = ollama_client.status()
    if not oll.running:
        cli_models = ollama_client.list_models_cli()
        if cli_models:
            registry.reconcile_with_ollama(cli_models)
    else:
        registry.reconcile_with_ollama(oll.models)
    models = registry.evaluate(report)
    net = offline.check(args.offline)

    if args.json:
        print(json.dumps({
            "hardware": report.to_dict(),
            "profile": result.to_dict(),
            "models": [m.to_dict() for m in models],
            "ollama": oll.__dict__,
            "offline": net.__dict__,
        }, indent=2))
    else:
        print(human(report, result, models, oll, net))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
