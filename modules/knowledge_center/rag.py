"""ADWIN OS — Knowledge Center RAG orchestrator.

Ingests documents into per-project libraries and answers questions using only
retrieved local context, with source references. Everything is local:
documents never leave the machine, embeddings come from a local model or the
lexical fallback, and generation uses the local Ollama LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from modules.knowledge_center import parsers, chunking
from modules.knowledge_center.embeddings import get_embedder, Embedder
from modules.knowledge_center.vector_store import VectorStore, Hit
from modules.chat import ollama_client

RAG_SYSTEM = (
    "You are ADWIN OS's Knowledge Center. Answer the user's question using ONLY "
    "the provided context passages. Cite the sources you used by their [n] "
    "marker. If the answer is not in the context, say you don't have that "
    "information in the knowledge base. Be concise and accurate."
)


@dataclass
class IngestResult:
    document: str
    chunks: int
    embedder: str
    kind: str


@dataclass
class Answer:
    answer: str
    sources: list[dict] = field(default_factory=list)
    embedder: str = ""
    model: str = ""
    used_context: bool = True


class KnowledgeCenter:
    def __init__(self, db_path: str | Path, ollama_host: str = "http://127.0.0.1:11434",
                 embed_model: str = "nomic-embed-text", prefer_model: bool = True):
        self.store = VectorStore(db_path)
        self.ollama_host = ollama_host
        self.embed_model = embed_model
        self.prefer_model = prefer_model

    def _embedder(self) -> Embedder:
        return get_embedder(prefer_model=self.prefer_model,
                            model=self.embed_model, host=self.ollama_host)

    # -- libraries -------------------------------------------------------- #
    def create_library(self, name: str) -> None:
        self.store.create_library(name)

    def list_libraries(self) -> list[dict]:
        return self.store.list_libraries()

    def list_documents(self, library: str) -> list[dict]:
        return self.store.list_documents(library)

    # -- ingest ----------------------------------------------------------- #
    def _ingest_parsed(self, library: str, doc, embedder: Embedder,
                       chunk_size: int, overlap: int) -> IngestResult:
        chunks = chunking.chunk_text(doc.text, chunk_size, overlap)
        if not chunks:
            raise parsers.ParserError(f"No text to index in {doc.source}")
        vectors = embedder.embed([c.text for c in chunks])
        triples = [(c.ordinal, c.text, v) for c, v in zip(chunks, vectors)]
        name = Path(doc.source).name if doc.source else "document"
        self.store.add_document(library, name, doc.source, doc.kind, triples, embedder.name)
        return IngestResult(document=name, chunks=len(chunks),
                            embedder=embedder.name, kind=doc.kind)

    def ingest_file(self, library: str, path: str, chunk_size: int = 900,
                    overlap: int = 150) -> IngestResult:
        doc = parsers.parse_file(path)
        return self._ingest_parsed(library, doc, self._embedder(), chunk_size, overlap)

    def ingest_text(self, library: str, name: str, text: str,
                    chunk_size: int = 900, overlap: int = 150) -> IngestResult:
        doc = parsers.parse_text(name, text)
        return self._ingest_parsed(library, doc, self._embedder(), chunk_size, overlap)

    def delete_document(self, library: str, name: str) -> bool:
        return self.store.delete_document(library, name)

    # -- retrieval + answer ---------------------------------------------- #
    def retrieve(self, library: str, question: str, top_k: int = 4) -> list[Hit]:
        embedder = self._embedder()
        qvec = embedder.embed([question])[0]
        return self.store.search(library, qvec, embedder.name, top_k)

    def ask(self, library: str, question: str, model: str,
            top_k: int = 4, min_score: float = 0.01) -> Answer:
        embedder = self._embedder()
        qvec = embedder.embed([question])[0]
        hits = [h for h in self.store.search(library, qvec, embedder.name, top_k)
                if h.score >= min_score]
        if not hits:
            return Answer(
                answer="I don't have information about that in this knowledge "
                       "base. Try ingesting relevant documents first.",
                sources=[], embedder=embedder.name, model=model, used_context=False)

        context_blocks = []
        sources = []
        for i, h in enumerate(hits, 1):
            context_blocks.append(f"[{i}] (from {h.document}, part {h.ordinal}):\n{h.text}")
            sources.append({"n": i, "document": h.document, "source": h.source,
                            "ordinal": h.ordinal, "score": round(h.score, 4)})
        context = "\n\n".join(context_blocks)
        prompt = (f"Context passages:\n{context}\n\n"
                  f"Question: {question}\n\n"
                  f"Answer using only the context above and cite sources as [n].")
        # Local-only guard.
        host = self.ollama_host
        if not (host.startswith("http://127.0.0.1") or host.startswith("http://localhost")):
            raise RuntimeError("Refusing non-local LLM endpoint in offline mode.")
        content = ollama_client.chat(prompt, model=model, host=host,
                                     system=RAG_SYSTEM, think=False)
        return Answer(answer=content, sources=sources, embedder=embedder.name,
                      model=model, used_context=True)
