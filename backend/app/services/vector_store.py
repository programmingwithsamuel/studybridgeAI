from dataclasses import dataclass
from threading import Lock
from typing import Any

from app.core.config import settings

COLLECTION_NAME = "studybridge_academic_chunks"
_client: Any | None = None
_collection: Any | None = None
_store_lock = Lock()


@dataclass(frozen=True)
class VectorHit:
    chunk_id: str
    text: str
    metadata: dict[str, Any]
    distance: float


def _get_collection() -> Any:
    global _client, _collection
    if _collection is None:
        with _store_lock:
            if _collection is None:
                import chromadb

                settings.CHAT_VECTOR_DB_PATH.mkdir(parents=True, exist_ok=True)
                _client = chromadb.PersistentClient(path=str(settings.CHAT_VECTOR_DB_PATH))
                _collection = _client.get_or_create_collection(
                    name=COLLECTION_NAME,
                    metadata={"hnsw:space": "cosine"},
                )
    return _collection


def upsert_chunks(chunks: list[dict[str, Any]], embeddings: list[list[float]]) -> None:
    if not chunks:
        raise ValueError("Cannot index a document with no extractable text.")
    if len(chunks) != len(embeddings):
        raise ValueError("Chunk and embedding counts do not match.")

    collection = _get_collection()
    collection.upsert(
        ids=[chunk["id"] for chunk in chunks],
        embeddings=embeddings,
        documents=[chunk["text"] for chunk in chunks],
        metadatas=[chunk["metadata"] for chunk in chunks],
    )

    document_id = chunks[0]["metadata"]["document_id"]
    content_hash = chunks[0]["metadata"]["content_hash"]
    existing = collection.get(
        where={"document_id": document_id},
        include=["metadatas"],
    )
    stale_ids = [
        chunk_id
        for chunk_id, metadata in zip(existing["ids"], existing["metadatas"] or [])
        if metadata.get("content_hash") != content_hash
    ]
    if stale_ids:
        collection.delete(ids=stale_ids)


def search_chunks(
    query_embedding: list[float],
    authorized_versions: dict[int, str],
    limit: int,
) -> list[VectorHit]:
    if not authorized_versions:
        return []
    collection = _get_collection()
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=limit,
        where={
            "$and": [
                {"document_id": {"$in": [str(document_id) for document_id in authorized_versions]}},
                {"content_hash": {"$in": list(authorized_versions.values())}},
            ]
        },
        include=["documents", "metadatas", "distances"],
    )
    hits: list[VectorHit] = []
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    ids = (result.get("ids") or [[]])[0]
    for chunk_id, text, metadata, distance in zip(ids, documents, metadatas, distances):
        document_id = int(metadata["document_id"])
        if authorized_versions.get(document_id) != metadata.get("content_hash"):
            continue
        hits.append(VectorHit(chunk_id, text, metadata, float(distance)))
    return hits


def remove_document_chunks(document_id: int) -> None:
    collection = _get_collection()
    collection.delete(where={"document_id": str(document_id)})


def remove_stale_chunks(active_versions: dict[int, str]) -> int:
    collection = _get_collection()
    existing = collection.get(include=["metadatas"])
    stale_ids = []
    for chunk_id, metadata in zip(existing["ids"], existing["metadatas"] or []):
        document_id = int(metadata["document_id"])
        if active_versions.get(document_id) != metadata.get("content_hash"):
            stale_ids.append(chunk_id)
    if stale_ids:
        collection.delete(ids=stale_ids)
    return len(stale_ids)
