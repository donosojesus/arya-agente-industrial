"""Documentacion de la planta para consulta (RAG local): carga, troceo por seccion y busqueda."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .textsearch import Bm25Index


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    title: str
    section: str
    text: str


class DocumentIndex:
    def __init__(self, directory: str) -> None:
        self.chunks: list[Chunk] = []
        self.documents: dict[str, str] = {}
        for path in sorted(Path(directory).glob("*.md")):
            self._load(path)
        # el titulo y la seccion tambien cuentan para la busqueda
        self._index = Bm25Index([f"{c.title} {c.section} {c.section} {c.text}" for c in self.chunks])

    def _load(self, path: Path) -> None:
        title, doc_id, section, lines = path.stem, path.stem, "", []

        def flush() -> None:
            text = " ".join(" ".join(lines).split())
            if section and text:
                self.chunks.append(Chunk(doc_id, title, section, text))

        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("# "):
                title = line[2:].strip()
            elif line.upper().startswith("ID:"):
                doc_id = line[3:].strip()
            elif line.startswith("## "):
                flush()
                section, lines = line[3:].strip(), []
            elif line:
                lines.append(line)
        flush()
        self.documents[doc_id] = title

    def search(self, query: str, limit: int = 3) -> list[dict[str, object]]:
        results = []
        for i, score in self._index.search(query, limit):
            chunk = self.chunks[i]
            results.append({"document_id": chunk.doc_id, "title": chunk.title, "section": chunk.section,
                            "text": chunk.text[:900], "score": score})
        return results
