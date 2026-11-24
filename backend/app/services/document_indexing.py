import re
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pymupdf
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.database import SessionLocal
from app.models import (
    Course,
    Department,
    Document,
    DocumentIndexStatus,
    DocumentStatus,
    Faculty,
    University,
)
from app.services.ai_embeddings import embed_texts
from app.services.vector_store import remove_document_chunks, upsert_chunks

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200
logger = logging.getLogger(__name__)


def split_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    if chunk_size < 1 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Chunk overlap must be non-negative and smaller than chunk size.")
    normalized = re.sub(r"\s+", " ", text).strip()
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind(" ", start + chunk_size // 2, end)
            if boundary > start:
                end = boundary
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(start + 1, end - overlap)
    return chunks


def extract_pdf_chunks(
    document: Document,
    course_code: str = "",
    university_name: str = "",
    faculty_name: str = "",
    department_name: str = "",
) -> list[dict[str, Any]]:
    path = Path(document.storage_path)
    if not path.is_file():
        raise FileNotFoundError(f"Stored PDF for document {document.id} is missing.")

    chunks: list[dict[str, Any]] = []
    with pymupdf.open(path) as pdf:
        for page_index, page in enumerate(pdf, start=1):
            page_chunks = split_text(page.get_text("text"))
            for chunk_index, text in enumerate(page_chunks):
                chunk_id = f"{document.id}:{document.sha256}:p{page_index}:c{chunk_index}"
                chunks.append({
                    "id": chunk_id,
                    "text": text,
                    "metadata": {
                        "document_id": str(document.id),
                        "document_title": document.title,
                        "content_hash": document.sha256,
                        "course_id": str(document.course_id or ""),
                        "course_code": course_code,
                        "university": university_name,
                        "faculty": faculty_name,
                        "department": department_name,
                        "page_number": page_index,
                    },
                })
    if not chunks:
        raise ValueError(f"Approved document {document.id} contains no extractable text.")
    return chunks


def _document_metadata(db: Session, document: Document) -> tuple[str, str, str, str]:
    course = db.get(Course, document.course_id) if document.course_id else None
    department = db.get(Department, course.department_id) if course else None
    faculty = db.get(Faculty, department.faculty_id) if department else None
    university = db.get(University, faculty.university_id) if faculty else None
    return (
        course.code if course else "",
        university.name if university else "",
        faculty.name if faculty else "",
        department.name if department else "",
    )


def index_approved_document(
    db: Session,
    document_id: int,
    *,
    embedder: Callable[[list[str]], list[list[float]]] = embed_texts,
    upsert: Any = upsert_chunks,
    remove: Any = remove_document_chunks,
) -> str:
    document = db.scalar(
        select(Document)
        .options(joinedload(Document.course))
        .where(Document.id == document_id)
    )
    index_state = db.get(DocumentIndexStatus, document_id)
    if document is None:
        remove(document_id)
        if index_state is not None:
            db.delete(index_state)
            db.commit()
        return "removed"
    if document.status != DocumentStatus.VERIFIED or document.withdrawn_at is not None:
        remove(document_id)
        if index_state is None:
            index_state = DocumentIndexStatus(document_id=document_id)
            db.add(index_state)
        index_state.status = "inactive"
        index_state.content_hash = document.sha256
        index_state.error = None
        index_state.updated_at = datetime.now(timezone.utc)
        db.commit()
        return "inactive"
    if (
        index_state is not None
        and index_state.status == "indexed"
        and index_state.content_hash == document.sha256
    ):
        return "already_indexed"

    if index_state is None:
        index_state = DocumentIndexStatus(document_id=document_id, status="indexing")
        db.add(index_state)
    else:
        index_state.status = "indexing"
        index_state.error = None
    index_state.content_hash = document.sha256
    index_state.updated_at = datetime.now(timezone.utc)
    db.commit()

    try:
        course_code, university, faculty, department = _document_metadata(db, document)
        chunks = extract_pdf_chunks(
            document,
            course_code,
            university,
            faculty,
            department,
        )
        vectors = embedder([chunk["text"] for chunk in chunks])
        upsert(chunks, vectors)
        index_state.status = "indexed"
        index_state.error = None
        index_state.indexed_at = datetime.now(timezone.utc)
        index_state.updated_at = datetime.now(timezone.utc)
        db.commit()
        return "indexed"
    except Exception as exc:
        db.rollback()
        failed_state = db.get(DocumentIndexStatus, document_id)
        if failed_state is None:
            failed_state = DocumentIndexStatus(document_id=document_id)
            db.add(failed_state)
        failed_state.content_hash = document.sha256
        failed_state.status = "failed"
        failed_state.error = f"{type(exc).__name__}: {exc}"[:500]
        failed_state.updated_at = datetime.now(timezone.utc)
        db.commit()
        raise


def process_approved_document(document_id: int) -> None:
    with SessionLocal() as db:
        try:
            index_approved_document(db, document_id)
        except Exception:
            logger.exception("Indexing failed for document %s.", document_id)


def remove_document_from_index(document_id: int) -> None:
    process_approved_document(document_id)
