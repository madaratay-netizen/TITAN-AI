"""TITAN AI — text chunking for RAG.

Splits a document into overlapping, roughly word-bounded chunks so retrieval
returns coherent passages. Pure standard library.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    ordinal: int
    text: str
    start: int
    end: int


_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    # Collapse excessive whitespace but keep paragraph boundaries.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 150) -> list[Chunk]:
    """Chunk text into ~chunk_size-character windows with `overlap` carryover.

    Breaks are nudged to the nearest whitespace so words aren't split.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be >= 0 and < chunk_size")

    text = _normalize(text)
    if not text:
        return []
    chunks: list[Chunk] = []
    n = len(text)
    start = 0
    ordinal = 0
    while start < n:
        end = min(start + chunk_size, n)
        if end < n:
            # Nudge end back to the last whitespace in the window (keep words whole).
            m = list(_WS.finditer(text, start, end))
            if m and m[-1].start() > start + chunk_size // 2:
                end = m[-1].start()
        piece = text[start:end].strip()
        if piece:
            chunks.append(Chunk(ordinal=ordinal, text=piece, start=start, end=end))
            ordinal += 1
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks
