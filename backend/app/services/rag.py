from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Document, DocumentCollection
from app.services.ollama import ollama_client

logger = logging.getLogger(__name__)


def sanitize_text(text: str) -> str:
    text = text.replace("\x00", "")
    return re.sub(r"[ \t]+\n", "\n", text).strip()


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    text = sanitize_text(text)
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        chunks.append(text[start:end])
        if end >= length:
            break
        start = max(0, end - overlap)
    return chunks


class RAGService:
    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings
        self._client: QdrantClient | None = None

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(url=self.settings.qdrant_url)
        return self._client

    def ensure_collection(self, name: str, vector_size: int = 768) -> None:
        existing = {c.name for c in self.client.get_collections().collections}
        if name in existing:
            return
        self.client.create_collection(
            collection_name=name,
            vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE),
        )

    async def health(self) -> bool:
        try:
            self.client.get_collections()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Qdrant health failed: %s", exc)
            return False

    async def embed(self, text: str) -> list[float]:
        return await ollama_client.embeddings(self.settings.embedding_model, text)

    async def index_document(
        self,
        session: AsyncSession,
        collection: DocumentCollection,
        document: Document,
        text: str,
    ) -> int:
        chunks = chunk_text(text, self.settings.chunk_size, self.settings.chunk_overlap)
        if not chunks:
            document.status = "empty"
            document.chunk_count = 0
            await session.commit()
            return 0

        first_vec = await self.embed(chunks[0])
        self.ensure_collection(collection.qdrant_collection, vector_size=len(first_vec))

        points: list[qmodels.PointStruct] = []
        vectors = [first_vec]
        for chunk in chunks[1:]:
            vectors.append(await self.embed(chunk))

        for idx, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            points.append(
                qmodels.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={
                        "document_id": str(document.id),
                        "collection_id": str(collection.id),
                        "filename": document.filename,
                        "chunk_index": idx,
                        "text": chunk,
                    },
                )
            )

        self.client.upsert(collection_name=collection.qdrant_collection, points=points)
        document.chunk_count = len(chunks)
        document.status = "indexed"
        document.error_message = None
        await session.commit()
        return len(chunks)

    async def search(self, collection_name: str, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        k = top_k or self.settings.rag_top_k
        vector = await self.embed(query)
        results = self.client.search(collection_name=collection_name, query_vector=vector, limit=k)
        return [
            {
                "score": hit.score,
                "text": (hit.payload or {}).get("text", ""),
                "filename": (hit.payload or {}).get("filename"),
                "document_id": (hit.payload or {}).get("document_id"),
            }
            for hit in results
        ]

    async def build_context(self, collection_name: str, query: str) -> str:
        hits = await self.search(collection_name, query)
        if not hits:
            return ""
        parts = [f"[{h.get('filename')}] {h.get('text')}" for h in hits]
        return "Relevant context:\n" + "\n---\n".join(parts)

    def delete_document_points(self, collection_name: str, document_id: str) -> None:
        self.client.delete(
            collection_name=collection_name,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[qmodels.FieldCondition(key="document_id", match=qmodels.MatchValue(value=document_id))]
                )
            ),
        )


def parse_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return sanitize_text("\n".join(pages))


def parse_markdown(path: Path) -> str:
    return sanitize_text(path.read_text(encoding="utf-8", errors="ignore"))


def parse_git_repo(repo_path: Path, extensions: set[str] | None = None) -> str:
    extensions = extensions or {".py", ".ts", ".tsx", ".js", ".md", ".go", ".rs", ".java", ".txt"}
    parts: list[str] = []
    for file in repo_path.rglob("*"):
        if not file.is_file():
            continue
        if file.suffix.lower() not in extensions:
            continue
        if any(p in {".git", "node_modules", ".venv", "dist", "build"} for p in file.parts):
            continue
        try:
            content = file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        parts.append(f"# File: {file.relative_to(repo_path)}\n{content}")
    return sanitize_text("\n\n".join(parts))


rag_service = RAGService()
