#!/usr/bin/env python3
"""TITAN AI — Offline Verification Test.

Checks what can be verified *right now* and reports each item honestly as
PASS / FAIL / SKIP. It does NOT assert full network isolation — that requires
an out-of-band network capture, and this harness will not claim it.

What it checks:
  1. Hardware detection runs and returns sane values.
  2. Adaptive engine produces a profile and load budgets.
  3. Local Ollama is reachable and a model is installed.
  4. A real local chat completes with internet-independent inference.
  5. Offline manager reports a coherent isolation level.

Run:  python scripts/offline_test.py
Exit code is non-zero if any non-skipped check FAILS.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.hardware_detection import detector          # noqa: E402
from core.adaptive_engine import engine                # noqa: E402
from modules.chat import ollama_client                 # noqa: E402
from core.offline_manager import offline               # noqa: E402

results: list[tuple[str, str, str]] = []  # (name, status, detail)


def record(name, status, detail=""):
    results.append((name, status, detail))
    mark = {"PASS": "✓", "FAIL": "✗", "SKIP": "–"}[status]
    print(f"[{mark}] {name}: {status}{(' — ' + detail) if detail else ''}")


def main() -> int:
    print("TITAN AI — Offline Verification Test\n" + "=" * 40)

    # 1. hardware detection
    try:
        rep = detector.detect()
        ok = rep.cpu.logical_cores >= 1 and rep.memory.total_gb > 0
        record("hardware_detection", "PASS" if ok else "FAIL",
               f"{rep.cpu.logical_cores} threads, {rep.memory.total_gb} GB RAM")
    except Exception as exc:
        record("hardware_detection", "FAIL", str(exc))
        rep = None

    # 2. adaptive engine
    if rep:
        try:
            res = engine.evaluate(rep)
            record("adaptive_engine", "PASS",
                   f"{res.profile.key} {res.profile.name}, "
                   f"RAM budget {res.ram_budget_gb} GB")
        except Exception as exc:
            record("adaptive_engine", "FAIL", str(exc))

    # 3. local model server
    st = ollama_client.status()
    if not st.running:
        record("local_model_server", "SKIP", "Ollama not running")
    elif not st.models:
        record("local_model_server", "FAIL", "Ollama running but no models installed")
    else:
        record("local_model_server", "PASS",
               f"Ollama v{st.version}, models: {', '.join(st.models)}")

    # 4. real local inference (internet-independent)
    if st.running and st.models:
        model = st.models[0]
        try:
            t0 = time.time()
            ans = ollama_client.chat(
                "Reply with exactly: OK", model=model,
                options={"num_predict": 20}, think=False, timeout=300)
            dt = time.time() - t0
            if ans.strip():
                record("local_inference", "PASS",
                       f"{model} answered in {dt:.1f}s")
            else:
                record("local_inference", "FAIL", "empty response")
        except Exception as exc:
            record("local_inference", "FAIL", str(exc))
    else:
        record("local_inference", "SKIP", "no local model available")

    # 5. offline manager
    net = offline.check(offline_mode_enabled=True)
    coherent = net.isolation_level in (
        "no_internet_requirement", "no_network_connectivity", "fully_isolated")
    record("offline_manager", "PASS" if coherent else "FAIL", net.isolation_level)

    # Honest note on isolation.
    print("\nNOTE: This harness verifies offline *operation*, not network "
          "*isolation*. 'fully_isolated' must be proven with an external packet "
          "capture before it is claimed.")

    failed = [r for r in results if r[1] == "FAIL"]
    skipped = [r for r in results if r[1] == "SKIP"]
    print(f"\nSummary: {len(results)-len(failed)-len(skipped)} passed, "
          f"{len(failed)} failed, {len(skipped)} skipped.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
