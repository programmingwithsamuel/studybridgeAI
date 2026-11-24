from threading import Lock

from app.core.config import settings


_model = None
_model_lock = Lock()


def embed_texts(texts: list[str]) -> list[list[float]]:
    global _model
    if not texts:
        return []
    if _model is None:
        with _model_lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                _model = SentenceTransformer(settings.CHAT_EMBEDDING_MODEL, device="cpu")
    vectors = _model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return vectors.tolist()
