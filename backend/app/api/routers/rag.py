from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.core.config import get_settings
from app.models import Document, DocumentCollection
from app.schemas import CollectionCreate, CollectionOut, DocumentOut
from app.services.rag import parse_git_repo, parse_markdown, parse_pdf, rag_service

router = APIRouter(prefix="/api/rag", tags=["rag"])


def _safe_collection_name(name: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_" else "_" for c in name.lower())
    return f"col_{cleaned[:40]}_{uuid4().hex[:8]}"


@router.post("/collections", response_model=CollectionOut, status_code=status.HTTP_201_CREATED)
async def create_collection(body: CollectionCreate, user: CurrentUser, db: DbSession) -> DocumentCollection:
    qname = _safe_collection_name(body.name)
    collection = DocumentCollection(
        user_id=user.id,
        name=body.name,
        description=body.description,
        qdrant_collection=qname,
        is_active=True,
    )
    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    rag_service.ensure_collection(qname, vector_size=768)
    return collection


@router.get("/collections", response_model=list[CollectionOut])
async def list_collections(user: CurrentUser, db: DbSession) -> list[DocumentCollection]:
    result = await db.execute(
        select(DocumentCollection).where(DocumentCollection.user_id == user.id).order_by(DocumentCollection.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/admin/collections", response_model=list[CollectionOut])
async def admin_list_collections(_: AdminUser, db: DbSession) -> list[DocumentCollection]:
    result = await db.execute(select(DocumentCollection).order_by(DocumentCollection.created_at.desc()))
    return list(result.scalars().all())


@router.post("/collections/{collection_id}/upload", response_model=DocumentOut)
async def upload_document(
    collection_id: UUID,
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
) -> Document:
    settings = get_settings()
    result = await db.execute(
        select(DocumentCollection).where(DocumentCollection.id == collection_id, DocumentCollection.user_id == user.id)
    )
    collection = result.scalar_one_or_none()
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")

    filename = file.filename or "upload.bin"
    suffix = Path(filename).suffix.lower()
    upload_root = Path(settings.upload_dir)
    upload_root.mkdir(parents=True, exist_ok=True)
    dest = upload_root / f"{uuid4().hex}{suffix}"
    content = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")
    dest.write_bytes(content)

    if suffix == ".pdf":
        source_type = "pdf"
        text = parse_pdf(dest)
    elif suffix in {".md", ".markdown", ".txt"}:
        source_type = "markdown"
        text = parse_markdown(dest)
    elif suffix == ".zip":
        source_type = "git"
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(dest, "r") as zf:
                zf.extractall(tmp)
            text = parse_git_repo(Path(tmp))
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")

    document = Document(
        collection_id=collection.id,
        filename=filename,
        source_type=source_type,
        storage_path=str(dest),
        status="processing",
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    try:
        await rag_service.index_document(db, collection, document, text)
    except Exception as exc:  # noqa: BLE001
        document.status = "error"
        document.error_message = str(exc)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    await db.refresh(document)
    return document


@router.post("/collections/{collection_id}/index-path", response_model=DocumentOut)
async def index_git_path(
    collection_id: UUID,
    user: CurrentUser,
    db: DbSession,
    path: str = Form(...),
) -> Document:
    """Index a local/mounted git checkout path (server-side)."""
    result = await db.execute(
        select(DocumentCollection).where(DocumentCollection.id == collection_id, DocumentCollection.user_id == user.id)
    )
    collection = result.scalar_one_or_none()
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    repo = Path(path)
    if not repo.exists() or not repo.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path not found on server")
    text = parse_git_repo(repo)
    document = Document(
        collection_id=collection.id,
        filename=str(repo),
        source_type="git",
        storage_path=str(repo),
        status="processing",
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    await rag_service.index_document(db, collection, document, text)
    await db.refresh(document)
    return document


@router.get("/collections/{collection_id}/documents", response_model=list[DocumentOut])
async def list_documents(collection_id: UUID, user: CurrentUser, db: DbSession) -> list[Document]:
    result = await db.execute(
        select(DocumentCollection).where(DocumentCollection.id == collection_id, DocumentCollection.user_id == user.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    docs = await db.execute(select(Document).where(Document.collection_id == collection_id))
    return list(docs.scalars().all())


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_document(document_id: UUID, user: CurrentUser, db: DbSession) -> Response:
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.collection))
        .where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()
    if document is None or document.collection.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    rag_service.delete_document_points(document.collection.qdrant_collection, str(document.id))
    if document.storage_path:
        path = Path(document.storage_path)
        if path.exists() and path.is_file():
            path.unlink(missing_ok=True)
    await db.delete(document)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/search")
async def search(
    user: CurrentUser,
    db: DbSession,
    collection_id: UUID = Form(...),
    query: str = Form(...),
) -> dict:
    result = await db.execute(
        select(DocumentCollection).where(DocumentCollection.id == collection_id, DocumentCollection.user_id == user.id)
    )
    collection = result.scalar_one_or_none()
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    hits = await rag_service.search(collection.qdrant_collection, query)
    return {"hits": hits}
