"""Knowledge Center (RAG) tests — deterministic, no model required.

These exercise chunking, the lexical embedder, the vector store, and retrieval
end-to-end using the zero-download lexical embedder, so they prove the pipeline
works on any machine.
"""
import os

from modules.knowledge_center import chunking, parsers
from modules.knowledge_center.embeddings import LexicalEmbedder, cosine, get_embedder
from modules.knowledge_center.vector_store import VectorStore
from modules.knowledge_center.rag import KnowledgeCenter


# -- chunking --------------------------------------------------------------- #
def test_chunk_basic():
    text = "word " * 500  # 2500 chars
    chunks = chunking.chunk_text(text, chunk_size=400, overlap=50)
    assert len(chunks) > 1
    assert all(len(c.text) <= 420 for c in chunks)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_chunk_empty():
    assert chunking.chunk_text("") == []


def test_chunk_overlap_validation():
    import pytest
    with pytest.raises(ValueError):
        chunking.chunk_text("x", chunk_size=100, overlap=100)


# -- embeddings ------------------------------------------------------------- #
def test_lexical_is_deterministic():
    e = LexicalEmbedder()
    v1 = e.embed(["the quick brown fox"])[0]
    v2 = e.embed(["the quick brown fox"])[0]
    assert v1 == v2
    assert len(v1) == e.dim


def test_lexical_similarity_ranks_related_higher():
    e = LexicalEmbedder()
    q = e.embed(["pump station maintenance schedule"])[0]
    related = e.embed(["the pump station maintenance is scheduled monthly"])[0]
    unrelated = e.embed(["banana bread recipe with walnuts"])[0]
    assert cosine(q, related) > cosine(q, unrelated)


# -- vector store + retrieval ---------------------------------------------- #
def test_store_ingest_and_search(tmp_path):
    db = tmp_path / "kc.db"
    store = VectorStore(db)
    e = LexicalEmbedder()
    texts = ["ADWIN runs fully offline on an external SSD.",
             "The honey filling line uses a dosing pump.",
             "Fire pumps must maintain 7 bar pressure."]
    chunks = [(i, t, e.embed([t])[0]) for i, t in enumerate(texts)]
    store.add_document("lib1", "doc.txt", "doc.txt", ".txt", chunks, e.name)
    qvec = e.embed(["what pressure must the fire pumps hold?"])[0]
    hits = store.search("lib1", qvec, e.name, top_k=1)
    assert hits and "Fire pumps" in hits[0].text


def test_store_replaces_document(tmp_path):
    store = VectorStore(tmp_path / "kc.db")
    e = LexicalEmbedder()
    c1 = [(0, "old text", e.embed(["old text"])[0])]
    c2 = [(0, "new text", e.embed(["new text"])[0])]
    store.add_document("l", "d.txt", "d.txt", ".txt", c1, e.name)
    store.add_document("l", "d.txt", "d.txt", ".txt", c2, e.name)
    docs = store.list_documents("l")
    assert len(docs) == 1 and docs[0]["chunks"] == 1


# -- parsers ---------------------------------------------------------------- #
def test_parse_txt(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hello world", encoding="utf-8")
    doc = parsers.parse_file(p)
    assert doc.text == "hello world" and doc.kind == ".txt"


def test_parse_csv(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("name,qty\npump,3\nvalve,7", encoding="utf-8")
    doc = parsers.parse_file(p)
    assert "pump | 3" in doc.text


def test_parse_unsupported(tmp_path):
    import pytest
    p = tmp_path / "a.zzz"
    p.write_text("x", encoding="utf-8")
    with pytest.raises(parsers.ParserError):
        parsers.parse_file(p)


# -- RAG orchestrator (retrieval path, no LLM) ----------------------------- #
def test_rag_retrieve_finds_relevant(tmp_path):
    kc = KnowledgeCenter(db_path=str(tmp_path / "kc.db"), prefer_model=False)
    kc.ingest_text("proj", "spec.txt",
                   "The reef irrigation project uses solar pumps. "
                   "Each greenhouse has a drip system. "
                   "Backup diesel generators provide power during outages.")
    hits = kc.retrieve("proj", "what provides power during an outage?", top_k=1)
    assert hits
    assert "diesel" in hits[0].text.lower()


def test_rag_ask_without_context_is_honest(tmp_path):
    kc = KnowledgeCenter(db_path=str(tmp_path / "kc.db"), prefer_model=False)
    kc.create_library("empty")
    ans = kc.ask("empty", "anything?", model="qwen3.5:4b")
    assert ans.used_context is False
    assert not ans.sources


def test_get_embedder_falls_back_to_lexical():
    # With a nonexistent host, it must fall back to the lexical embedder.
    e = get_embedder(prefer_model=True, host="http://127.0.0.1:1")
    assert e.name == "lexical-hash-512"
