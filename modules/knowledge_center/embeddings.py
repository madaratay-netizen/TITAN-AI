"""ADWIN OS — local embeddings for RAG.

Two backends, both fully offline:

* OllamaEmbedder  — semantic embeddings from a local model (nomic-embed-text).
                    Best quality; requires the model to be pulled.
* LexicalEmbedder — deterministic hashed bag-of-words vectors. Zero downloads,
                    zero dependencies. Lower quality but always available, so
                    the Knowledge Center works on any machine out of the box.

`get_embedder()` prefers the Ollama model when it is installed and reachable,
otherwise falls back to lexical — and always reports which one it used.
"""
from __future__ import annotations

import json
import math
import re
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass
from typing import Protocol

DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_EMBED_MODEL = "nomic-embed-text"
_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity. Assumes equal length; handles zero vectors."""
    if len(a) != len(b):
        raise ValueError("vector length mismatch")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class Embedder(Protocol):
    name: str
    dim: int
    def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass
class LexicalEmbedder:
    """Hashed bag-of-words with sublinear term frequency, L2-normalized."""
    dim: int = 512
    name: str = "lexical-hash-512"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            counts: dict[int, int] = {}
            for tok in _tokenize(text):
                # Deterministic hash (NOT builtin hash(), which is per-process
                # randomized and would break retrieval across restarts).
                h = zlib.crc32(tok.encode("utf-8")) % self.dim
                counts[h] = counts.get(h, 0) + 1
            for idx, c in counts.items():
                vec[idx] = 1.0 + math.log(c)  # sublinear tf
            out.append(_l2_normalize(vec))
        return out


@dataclass
class OllamaEmbedder:
    model: str = DEFAULT_EMBED_MODEL
    host: str = DEFAULT_OLLAMA_HOST
    dim: int = 0  # discovered on first call
    name: str = ""

    def __post_init__(self):
        self.name = f"ollama:{self.model}"

    def _embed_one(self, text: str) -> list[float]:
        payload = json.dumps({"model": self.model, "input": text}).encode()
        req = urllib.request.Request(self.host + "/api/embed", data=payload,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        embs = data.get("embeddings") or []
        if not embs:
            raise RuntimeError("Ollama returned no embeddings")
        return embs[0]

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = self._embed_one(t)
            if not self.dim:
                self.dim = len(v)
            out.append(v)
        return out


def _ollama_has_model(model: str, host: str) -> bool:
    try:
        req = urllib.request.Request(host + "/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return False
    names = [m.get("name", "") for m in data.get("models", [])]
    return any(n == model or n.startswith(model + ":") for n in names)


def get_embedder(prefer_model: bool = True,
                 model: str = DEFAULT_EMBED_MODEL,
                 host: str = DEFAULT_OLLAMA_HOST) -> Embedder:
    """Return the best available embedder, preferring the local model."""
    if prefer_model and _ollama_has_model(model, host):
        return OllamaEmbedder(model=model, host=host)
    return LexicalEmbedder()
