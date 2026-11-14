"""ADWIN OS — IT & Cyber Lab log analysis (read-only).

Summarizes a log by severity, surfaces the most recent errors, and flags
frequent error signatures. Accepts pasted text, or a file confined to an
allowed directory (defaults to the ADWIN storage dir).
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

LEVELS = ["CRITICAL", "FATAL", "ERROR", "WARN", "WARNING", "INFO", "DEBUG"]
_LEVEL_RE = re.compile(r"\b(CRITICAL|FATAL|ERROR|WARN(?:ING)?|INFO|DEBUG)\b", re.I)
# Strip volatile bits so similar errors group together.
_NORMALIZE = [
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}\S*"), "<ts>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<hex>"),
    (re.compile(r"\b\d+\b"), "<n>"),
    (re.compile(r"(/[^ \t]+)+"), "<path>"),
]
MAX_BYTES = 5 * 1024 * 1024


def _normalize(line: str) -> str:
    s = line
    for rx, rep in _NORMALIZE:
        s = rx.sub(rep, s)
    return s.strip()[:200]


def analyze_text(text: str, recent: int = 15) -> dict:
    counts: Counter = Counter()
    error_lines: list[tuple[int, str]] = []
    signatures: Counter = Counter()
    total = 0
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        total += 1
        m = _LEVEL_RE.search(line)
        level = m.group(1).upper() if m else None
        if level == "WARN":
            level = "WARNING"
        if level:
            counts[level] += 1
        if level in ("ERROR", "CRITICAL", "FATAL"):
            error_lines.append((i, line.strip()[:300]))
            signatures[_normalize(line)] += 1
    top_sigs = [{"signature": s, "count": c} for s, c in signatures.most_common(5)]
    return {
        "total_lines": total,
        "by_level": {lvl: counts.get(lvl, 0) for lvl in
                     ["CRITICAL", "FATAL", "ERROR", "WARNING", "INFO", "DEBUG"]
                     if counts.get(lvl, 0)},
        "error_count": counts.get("ERROR", 0) + counts.get("CRITICAL", 0) + counts.get("FATAL", 0),
        "recent_errors": [{"line": n, "text": t} for n, t in error_lines[-recent:]],
        "top_error_signatures": top_sigs,
    }


def analyze_file(path: str, allowed_root: str | Path, recent: int = 15) -> dict:
    root = Path(allowed_root).resolve()
    target = (root / path.lstrip("/\\")).resolve() if not Path(path).is_absolute() \
        else Path(path).resolve()
    # Confinement: the file must live under the allowed root.
    if target != root and root not in target.parents:
        raise ValueError("log path escapes the allowed directory")
    if not target.is_file():
        raise FileNotFoundError(f"not a file: {path}")
    if target.stat().st_size > MAX_BYTES:
        raise ValueError(f"log too large (> {MAX_BYTES} bytes)")
    text = target.read_text(encoding="utf-8", errors="replace")
    result = analyze_text(text, recent)
    result["source"] = str(target)
    return result
