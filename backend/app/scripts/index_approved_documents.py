import logging

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Document, DocumentStatus
from app.services.document_indexing import index_approved_document
from app.services.vector_store import remove_stale_chunks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    with SessionLocal() as db:
        documents = db.scalars(
            select(Document).where(
                Document.status == DocumentStatus.VERIFIED,
                Document.withdrawn_at.is_(None),
            )
        ).all()
        active_versions = {document.id: document.sha256 for document in documents}
        indexed = 0
        failed = 0
        for document in documents:
            try:
                outcome = index_approved_document(db, document.id)
                indexed += outcome in {"indexed", "already_indexed"}
            except Exception:
                failed += 1
                logger.exception("Could not index approved document %s.", document.id)
        removed = remove_stale_chunks(active_versions)
        logger.info(
            "Indexing complete: %d approved documents, %d failed, %d stale chunks removed.",
            indexed,
            failed,
            removed,
        )


if __name__ == "__main__":
    main()
