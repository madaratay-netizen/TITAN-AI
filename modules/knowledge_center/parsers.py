"""TITAN AI — Knowledge Center document parsers.

Extracts plain text from supported document types for RAG ingestion. Each
parser degrades gracefully: if an optional library is missing, it raises a
clear ParserError naming the dependency rather than crashing the system.

Supported: .txt .md .markdown .csv .tsv .log  (stdlib)
            .pdf (pypdf) .docx (python-docx) .xlsx (openpyxl)
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path


class ParserError(Exception):
    """Raised when a document cannot be parsed (bad file or missing dep)."""


@dataclass
class ParsedDoc:
    source: str                       # file path or logical name
    text: str
    kind: str                         # extension / type
    pages: int = 1
    meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
PLAINTEXT = {".txt", ".md", ".markdown", ".log", ""}
TABULAR = {".csv", ".tsv"}
SUPPORTED = PLAINTEXT | TABULAR | {".pdf", ".docx", ".xlsx"}


def supported_extensions() -> list[str]:
    return sorted(e for e in SUPPORTED if e)


def _read_plaintext(path: Path) -> ParsedDoc:
    text = path.read_text(encoding="utf-8", errors="replace")
    return ParsedDoc(source=str(path), text=text, kind=path.suffix or ".txt")


def _read_tabular(path: Path) -> ParsedDoc:
    delim = "\t" if path.suffix.lower() == ".tsv" else ","
    rows = []
    with path.open(encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.reader(fh, delimiter=delim):
            rows.append(" | ".join(cell.strip() for cell in row))
    return ParsedDoc(source=str(path), text="\n".join(rows),
                     kind=path.suffix.lower(), meta={"rows": len(rows)})


def _read_pdf(path: Path) -> ParsedDoc:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as exc:
        raise ParserError("PDF support needs 'pypdf' (pip install pypdf)") from exc
    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # corrupt/encrypted
        raise ParserError(f"Could not read PDF: {exc}") from exc
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            parts.append("")
    text = "\n\n".join(parts).strip()
    if not text:
        raise ParserError("PDF has no extractable text (scanned? needs OCR).")
    return ParsedDoc(source=str(path), text=text, kind=".pdf",
                     pages=len(reader.pages))


def _read_docx(path: Path) -> ParsedDoc:
    try:
        import docx  # type: ignore
    except ImportError as exc:
        raise ParserError("DOCX support needs 'python-docx'") from exc
    try:
        doc = docx.Document(str(path))
    except Exception as exc:
        raise ParserError(f"Could not read DOCX: {exc}") from exc
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    return ParsedDoc(source=str(path), text="\n".join(parts), kind=".docx")


def _read_xlsx(path: Path) -> ParsedDoc:
    try:
        import openpyxl  # type: ignore
    except ImportError as exc:
        raise ParserError("XLSX support needs 'openpyxl'") from exc
    try:
        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    except Exception as exc:
        raise ParserError(f"Could not read XLSX: {exc}") from exc
    parts = []
    for ws in wb.worksheets:
        parts.append(f"# Sheet: {ws.title}")
        for row in ws.iter_rows(values_only=True):
            cells = ["" if v is None else str(v) for v in row]
            if any(cells):
                parts.append(" | ".join(cells))
    wb.close()
    return ParsedDoc(source=str(path), text="\n".join(parts), kind=".xlsx",
                     meta={"sheets": len(wb.worksheets)})


_DISPATCH = {
    ".pdf": _read_pdf,
    ".docx": _read_docx,
    ".xlsx": _read_xlsx,
}


def parse_file(path: str | Path) -> ParsedDoc:
    """Parse a document on disk into plain text."""
    p = Path(path)
    if not p.exists():
        raise ParserError(f"File not found: {p}")
    if not p.is_file():
        raise ParserError(f"Not a file: {p}")
    ext = p.suffix.lower()
    if ext in _DISPATCH:
        return _DISPATCH[ext](p)
    if ext in TABULAR:
        return _read_tabular(p)
    if ext in PLAINTEXT:
        return _read_plaintext(p)
    raise ParserError(
        f"Unsupported file type '{ext}'. Supported: {', '.join(supported_extensions())}")


def parse_text(name: str, text: str, kind: str = ".txt") -> ParsedDoc:
    """Wrap raw text (e.g. pasted into the dashboard) as a ParsedDoc."""
    return ParsedDoc(source=name, text=text, kind=kind)
