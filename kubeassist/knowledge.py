"""Local knowledge base used to ground answers.

Documents are split into overlapping chunks. Retrieval uses a vector index when
``KUBEASSIST_VECTOR_SEARCH=1`` and the optional ``chromadb`` / ``sentence-transformers``
packages are installed; otherwise a dependency-free keyword scorer is used.
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)
TOKEN = re.compile(r"[a-z0-9][a-z0-9\-]+")
STOP = {"the", "and", "for", "how", "what", "with", "you", "can", "this", "that", "are", "does", "from",
        "is", "an", "of", "to", "in", "on", "it", "or", "be", "do", "me", "my", "a", "show", "tell", "explain"}


@dataclass(frozen=True)
class Chunk:
    source: str
    text: str

    @property
    def kind(self) -> str:
        """"examples" for request→command pairs (model grounding), otherwise "prose"."""
        return "examples" if "\nCommand:" in self.text else "prose"


def split_text(text: str, size: int = 700, overlap: int = 120) -> list[str]:
    """Split on paragraph boundaries; a short trailing paragraph is repeated as overlap."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current, last = "", ""
    for para in paragraphs:
        if current and len(current) + len(para) > size:
            chunks.append(current)
            current = f"{last}\n\n{para}" if last and len(last) <= overlap else para
        else:
            current = f"{current}\n\n{para}" if current else para
        last = para
    if current:
        chunks.append(current)
    return chunks


def tidy(text: str, limit: int = 600) -> str:
    """Make a raw chunk readable in chat: drop markdown headings, unwrap hard line breaks."""
    paras = []
    for block in re.split(r"\n\s*\n", text):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
        if lines:
            paras.append(" ".join(lines))
    out = "\n\n".join(paras)
    if len(out) > limit:
        out = out[:limit].rsplit(" ", 1)[0] + " …"
    return out


def _stem(term: str) -> str:
    return term[:-1] if len(term) > 3 and term.endswith("s") and not term.endswith("ss") else term


def _terms(text: str) -> list[str]:
    return [_stem(t) for t in TOKEN.findall(text.lower()) if t not in STOP]


class KnowledgeBase:
    def __init__(self, directory: Path, persist_dir: Path | None = None,
                 use_vectors: bool = False, embedding_model: str = ""):
        self.chunks: list[Chunk] = []
        self._vector = None
        self._load(Path(directory))
        self._df = Counter(t for c in self.chunks for t in set(_terms(c.text)))
        if use_vectors and persist_dir is not None:
            self._vector = self._try_vector_index(Path(persist_dir), embedding_model)

    @property
    def backend(self) -> str:
        return "vector" if self._vector else "keyword"

    def _load(self, directory: Path) -> None:
        if not directory.is_dir():
            log.warning("Knowledge directory %s does not exist", directory)
            return
        for path in sorted([*directory.glob("*.md"), *directory.glob("*.txt")]):
            for piece in split_text(path.read_text(encoding="utf-8")):
                self.chunks.append(Chunk(path.name, piece))
        log.info("Knowledge base: %d chunks", len(self.chunks))

    def _try_vector_index(self, persist_dir: Path, model: str):
        try:
            import chromadb
            from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

            client = chromadb.PersistentClient(path=str(persist_dir))
            embed = SentenceTransformerEmbeddingFunction(model_name=model)
            try:
                client.delete_collection("kubeassist")
            except Exception:  # collection may not exist yet
                pass
            col = client.create_collection("kubeassist", embedding_function=embed)
            if self.chunks:
                col.add(ids=[f"c{i}" for i in range(len(self.chunks))],
                        documents=[c.text for c in self.chunks],
                        metadatas=[{"source": c.source} for c in self.chunks])
            return col
        except Exception as exc:  # optional dependency or model download failed
            log.warning("Vector search unavailable (%s); using keyword search.", exc)
            return None

    def search(self, query: str, k: int = 3, kind: str | None = None) -> list[Chunk]:
        """Top-``k`` chunks for ``query``; ``kind`` restricts to "prose" or "examples"."""
        if not self.chunks:
            return []
        if self._vector is not None:
            try:
                n = min(k * 3 if kind else k, len(self.chunks))
                res = self._vector.query(query_texts=[query], n_results=n)
                hits = [Chunk(m["source"], d) for d, m in zip(res["documents"][0], res["metadatas"][0])]
                return [h for h in hits if kind in (None, h.kind)][:k]
            except Exception as exc:
                log.warning("Vector query failed (%s); falling back to keywords.", exc)
        return self._keyword_search(query, k, kind)

    def _keyword_search(self, query: str, k: int, kind: str | None = None) -> list[Chunk]:
        """Okapi BM25 over chunks (k1=1.4, b=0.75)."""
        q_terms = set(_terms(query))
        n = len(self.chunks)
        lengths = [len(_terms(c.text)) for c in self.chunks]
        avg_len = (sum(lengths) / n) or 1.0
        scored = []
        for chunk, length in zip(self.chunks, lengths):
            if kind and chunk.kind != kind:
                continue
            counts = Counter(_terms(chunk.text))
            score = 0.0
            for t in q_terms:
                tf = counts[t]
                if not tf:
                    continue
                idf = math.log(1 + (n - self._df[t] + 0.5) / (self._df[t] + 0.5))
                score += idf * tf * 2.4 / (tf + 1.4 * (0.25 + 0.75 * length / avg_len))
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda s: s[0], reverse=True)
        return [c for _, c in scored[:k]]

    def context_for(self, query: str, k: int = 3) -> str:
        return "\n---\n".join(c.text for c in self.search(query, k))
