import sys
from pathlib import Path
from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import pymupdf
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.auth import get_current_user
from app.api import chat as chat_api
from app.core.database import Base, get_db
from app.main import app
from app.models import (
    ChatMessage,
    ChatSession,
    Document,
    DocumentIndexStatus,
    DocumentStatus,
    User,
    UserRole,
)
from app.services import academic_chat, vector_store
from app.services.academic_chat import SourceReference, answer_question, retrieve_sources
from app.services.chat_provider import (
    ChatProviderError,
    GeminiProvider,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.services.document_indexing import extract_pdf_chunks, index_approved_document, split_text
from app.services.vector_store import VectorHit


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = test_sessions()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def make_user(db: Session, email: str, role: UserRole = UserRole.STUDENT) -> User:
    user = User(
        full_name=email.split("@")[0],
        email=email,
        password_hash="test-password-hash",
        role=role,
        is_active=True,
        email_verified=True,
    )
    db.add(user)
    db.flush()
    return user


def make_document(
    db: Session,
    user: User,
    title: str,
    *,
    status: DocumentStatus = DocumentStatus.VERIFIED,
    sha256: str = "a" * 64,
    withdrawn: bool = False,
) -> Document:
    document = Document(
        title=title,
        description=None,
        original_filename=f"{title}.pdf",
        storage_path="unused.pdf",
        sha256=sha256,
        file_size=100,
        uploaded_by_id=user.id,
        course_id=None,
        status=status,
        withdrawn_at=None if not withdrawn else datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    db.add(document)
    db.flush()
    return document


def test_split_text_keeps_overlap_and_pdf_chunks_keep_page_metadata(tmp_path):
    text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 3
    chunks = split_text(text, chunk_size=20, overlap=5)
    assert len(chunks) > 1
    assert chunks[0][-5:] == chunks[1][:5]

    pdf_path = tmp_path / "lecture.pdf"
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "First page academic material.")
    pdf.new_page().insert_text((72, 72), "Second page academic material.")
    pdf.save(pdf_path)
    pdf.close()
    document = Document(
        id=17,
        title="Lecture notes",
        original_filename="lecture.pdf",
        storage_path=str(pdf_path),
        sha256="f" * 64,
        file_size=pdf_path.stat().st_size,
        uploaded_by_id=1,
        status=DocumentStatus.VERIFIED,
    )

    result = extract_pdf_chunks(document, course_code="BIO 101")
    assert [chunk["metadata"]["page_number"] for chunk in result] == [1, 2]
    assert all(chunk["metadata"]["document_id"] == "17" for chunk in result)
    assert all(chunk["metadata"]["course_code"] == "BIO 101" for chunk in result)
    assert "Second page" in result[1]["text"]


def test_index_approved_document_is_idempotent(db, tmp_path):
    user = make_user(db, "lecturer@example.com", UserRole.LECTURER)
    pdf_path = tmp_path / "approved.pdf"
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "Approved course material.")
    pdf.save(pdf_path)
    pdf.close()
    document = make_document(db, user, "Approved notes")
    document.storage_path = str(pdf_path)
    chunks_upserted = []

    def upsert(chunks, vectors):
        chunks_upserted.extend(chunks)
        assert len(chunks) == len(vectors)

    args = {
        "embedder": lambda texts: [[1.0, 0.0] for _ in texts],
        "upsert": upsert,
        "remove": lambda document_id: None,
    }
    assert index_approved_document(db, document.id, **args) == "indexed"
    assert index_approved_document(db, document.id, **args) == "already_indexed"
    state = db.get(DocumentIndexStatus, document.id)
    assert state.status == "indexed"
    assert chunks_upserted


def test_retrieval_restricts_search_to_approved_current_authorized_documents(db, monkeypatch):
    user = make_user(db, "student@example.com", UserRole.ADMINISTRATOR)
    allowed = make_document(db, user, "Accessible notes", sha256="1" * 64)
    restricted = make_document(db, user, "Restricted notes", sha256="2" * 64)
    pending = make_document(db, user, "Pending notes", status=DocumentStatus.PENDING_REVIEW)
    withdrawn = make_document(db, user, "Withdrawn notes", withdrawn=True)
    for document in (allowed, restricted, pending, withdrawn):
        db.add(DocumentIndexStatus(
            document_id=document.id,
            content_hash=document.sha256,
            status="indexed",
        ))
    db.flush()
    monkeypatch.setattr(academic_chat, "_can_view", lambda db, document, user: document.id == allowed.id)
    queried_versions = {}

    def search(embedding, authorized_versions, limit):
        queried_versions.update(authorized_versions)
        return [
            VectorHit(
                chunk_id="allowed",
                text="Supported accessible excerpt.",
                metadata={
                    "document_id": str(allowed.id),
                    "content_hash": allowed.sha256,
                    "page_number": 3,
                    "document_title": allowed.title,
                },
                distance=0.1,
            ),
            VectorHit(
                chunk_id="restricted",
                text="Must never be returned.",
                metadata={
                    "document_id": str(restricted.id),
                    "content_hash": restricted.sha256,
                    "page_number": 9,
                },
                distance=0.01,
            ),
        ]

    sources = retrieve_sources(
        db,
        user,
        "Explain the topic",
        embedder=lambda texts: [[0.1, 0.2]],
        vector_search=search,
    )
    assert queried_versions == {allowed.id: allowed.sha256}
    assert len(sources) == 1
    assert sources[0].document_id == allowed.id
    assert sources[0].page_number == 3
    assert sources[0].excerpt == "Supported accessible excerpt."


def test_chat_followup_uses_user_history_and_persists_citation_shape(db):
    user = make_user(db, "history@example.com")
    session = ChatSession(user_id=user.id, title="Cell biology")
    db.add(session)
    db.flush()
    db.add_all([
        ChatMessage(session_id=session.id, role="user", content="Explain osmosis"),
        ChatMessage(session_id=session.id, role="assistant", content="Old answer with restricted details"),
    ])
    db.flush()
    source = SourceReference(
        document_id=5,
        document_title="Biology notes",
        page_number=4,
        excerpt="Water moves across a selectively permeable membrane.",
        course_code="BIO 101",
        university="Example University",
        faculty="Science",
        department="Biology",
    )
    observed = {}

    class FakeProvider:
        def generate(self, prompt):
            observed["prompt"] = prompt
            return "Osmosis is water movement. [1]"

    def retriever(db, user, query):
        observed["query"] = query
        return [source]

    answer, sources = answer_question(
        db,
        user,
        session.id,
        "Give an example",
        provider=FakeProvider(),
        retriever=retriever,
    )
    assert answer.endswith("[1]")
    assert "Explain osmosis" in observed["query"]
    assert "Old answer with restricted details" not in observed["query"]
    assert "Biology notes (document 5, page 4)" in observed["prompt"]
    assert sources == [source]


def test_simple_greeting_skips_embedding_and_gemini(db):
    user = make_user(db, "greeting@example.com")
    session = ChatSession(user_id=user.id, title="Greeting")
    db.add(session)
    db.flush()

    def unexpected_call(*args, **kwargs):
        raise AssertionError("A simple greeting should not call retrieval or Gemini.")

    answer, sources = answer_question(
        db,
        user,
        session.id,
        "  How are you? ",
        provider=SimpleNamespace(generate=unexpected_call),
        retriever=unexpected_call,
    )

    assert answer == "I'm here and ready to help with your studies. What would you like to learn about?"
    assert sources == []


@pytest.mark.parametrize(
    "question, expected",
    [
        ("hi", "Hi!"),
        ("What are you?", "I'm StudyBridge AI"),
        ("what time is it", "The current time on this server is"),
        ("what's today's date?", "Today is"),
    ],
)
def test_common_smalltalk_skips_embedding_and_gemini(db, question, expected):
    user = make_user(db, f"smalltalk-{len(question)}@example.com")
    session = ChatSession(user_id=user.id, title="Quick question")
    db.add(session)
    db.flush()

    def unexpected_call(*args, **kwargs):
        raise AssertionError("Common small talk should not call retrieval or Gemini.")

    answer, sources = answer_question(
        db,
        user,
        session.id,
        question,
        provider=SimpleNamespace(generate=unexpected_call),
        retriever=unexpected_call,
    )
    assert answer.startswith(expected)
    assert sources == []


def test_prompt_restricts_unrelated_questions_even_without_retrieved_sources():
    prompt = academic_chat.build_prompt("Tell me a celebrity gossip story", [], [])
    assert "Do not answer unrelated questions" in prompt
    assert "No approved accessible course excerpts" in prompt


def test_gemini_provider_streams_text_with_low_latency_configuration(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    chunks = [
        SimpleNamespace(text="First "),
        SimpleNamespace(text="answer."),
    ]
    request_options = {}

    def generate_content_stream(**kwargs):
        request_options.update(kwargs)
        return iter(chunks)

    client = SimpleNamespace(
        models=SimpleNamespace(generate_content_stream=generate_content_stream)
    )
    result = list(GeminiProvider(client).stream("Explain a course concept"))

    assert result == ["First ", "answer."]
    assert request_options["config"] == {
        "thinking_config": {"thinking_level": "minimal"},
        "max_output_tokens": 1024,
    }


def test_gemini_stream_falls_back_to_interactions_on_upstream_503(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")

    class ServiceUnavailableError(Exception):
        code = 503

    def raise_unavailable(**kwargs):
        raise ServiceUnavailableError()

    events = [
        SimpleNamespace(
            event_type="step.delta",
            delta=SimpleNamespace(type="text", text="Fallback answer."),
        ),
    ]
    interaction_options = {}

    def create_interaction(**kwargs):
        interaction_options.update(kwargs)
        return iter(events)

    client = SimpleNamespace(
        models=SimpleNamespace(generate_content_stream=raise_unavailable),
        interactions=SimpleNamespace(create=create_interaction),
    )
    assert list(GeminiProvider(client).stream("Question")) == ["Fallback answer."]
    assert interaction_options["stream"] is True


def test_gemini_generation_falls_back_to_interactions_on_upstream_503(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")

    class ServiceUnavailableError(Exception):
        code = 503

    def raise_unavailable(**kwargs):
        raise ServiceUnavailableError()

    interaction_options = {}

    def create_interaction(**kwargs):
        interaction_options.update(kwargs)
        return SimpleNamespace(output_text="Fallback answer.")

    client = SimpleNamespace(
        models=SimpleNamespace(generate_content=raise_unavailable),
        interactions=SimpleNamespace(create=create_interaction),
    )
    assert GeminiProvider(client).generate("Question") == "Fallback answer."
    assert interaction_options["store"] is False


def test_streaming_chat_endpoint_sends_and_persists_answer(db, monkeypatch):
    user = make_user(db, "stream-chat@example.com")
    session = ChatSession(user_id=user.id, title="Quick chat")
    db.add(session)
    db.commit()
    session_id = session.id

    def override_db():
        yield db

    monkeypatch.setitem(app.dependency_overrides, get_db, override_db)
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: user)
    monkeypatch.setattr(chat_api, "SessionLocal", lambda: nullcontext(db))

    response = TestClient(app).post(
        f"/api/chat/sessions/{session_id}/messages/stream",
        json={"message": "hi"},
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert '"type": "delta"' in response.text
    assert "Hi! What would you like to study today?" in response.text
    assert '"type": "done"' in response.text
    stored = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).all()
    assert [message.role for message in stored] == ["user", "assistant"]


def test_chat_session_cannot_be_read_or_deleted_by_another_user(db, monkeypatch):
    owner = make_user(db, "owner@example.com")
    other_user = make_user(db, "other@example.com")
    session = ChatSession(user_id=owner.id, title="Owner conversation")
    db.add(session)
    db.commit()
    session_id = session.id
    user_holder = {"current": other_user}

    def override_db():
        yield db

    monkeypatch.setitem(app.dependency_overrides, get_db, override_db)
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: user_holder["current"])
    client = TestClient(app)
    assert client.get(f"/api/chat/sessions/{session_id}").status_code == 404
    assert client.delete(f"/api/chat/sessions/{session_id}").status_code == 404
    user_holder["current"] = owner
    assert client.get(f"/api/chat/sessions/{session_id}").status_code == 200


def test_gemini_provider_surfaces_missing_key_rate_limit_timeout_and_empty_response(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    with pytest.raises(ProviderConfigurationError):
        GeminiProvider().generate("Question")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")

    class RateLimitError(Exception):
        code = 429

    def raise_rate_limit(**kwargs):
        raise RateLimitError()

    rate_limited_client = SimpleNamespace(
        models=SimpleNamespace(generate_content=raise_rate_limit)
    )
    with pytest.raises(ProviderRateLimitError):
        GeminiProvider(rate_limited_client).generate("Question")

    class ForbiddenError(Exception):
        code = 403

    def raise_forbidden(**kwargs):
        raise ForbiddenError()

    forbidden_client = SimpleNamespace(
        models=SimpleNamespace(generate_content=raise_forbidden)
    )
    with pytest.raises(ProviderConfigurationError, match="API key|API access"):
        GeminiProvider(forbidden_client).generate("Question")

    class ModelMissingError(Exception):
        code = 404

    def raise_model_missing(**kwargs):
        raise ModelMissingError()

    missing_model_client = SimpleNamespace(
        models=SimpleNamespace(generate_content=raise_model_missing)
    )
    with pytest.raises(ProviderConfigurationError, match="model"):
        GeminiProvider(missing_model_client).generate("Question")

    class ServiceUnavailableError(Exception):
        code = 503

    def raise_service_unavailable(**kwargs):
        raise ServiceUnavailableError()

    unavailable_client = SimpleNamespace(
        models=SimpleNamespace(generate_content=raise_service_unavailable),
        interactions=SimpleNamespace(create=raise_service_unavailable),
    )
    with pytest.raises(ProviderUnavailableError, match="temporarily unavailable"):
        GeminiProvider(unavailable_client).generate("Question")

    def raise_timeout(**kwargs):
        raise TimeoutError()

    timeout_client = SimpleNamespace(
        models=SimpleNamespace(generate_content=raise_timeout)
    )
    with pytest.raises(ProviderTimeoutError):
        GeminiProvider(timeout_client).generate("Question")

    empty_client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=lambda **kwargs: SimpleNamespace(text="  ")
        )
    )
    with pytest.raises(ChatProviderError):
        GeminiProvider(empty_client).generate("Question")


def test_persistent_chroma_retrieval_applies_authorized_document_filter(tmp_path, monkeypatch):
    monkeypatch.setattr(vector_store.settings, "CHAT_VECTOR_DB_PATH", tmp_path / "chroma")
    monkeypatch.setattr(vector_store, "_client", None)
    monkeypatch.setattr(vector_store, "_collection", None)
    first_hash = "1" * 64
    second_hash = "2" * 64

    vector_store.upsert_chunks(
        [{
            "id": "1:first",
            "text": "first accessible material",
            "metadata": {
                "document_id": "1",
                "content_hash": first_hash,
                "page_number": 1,
            },
        }],
        [[1.0, 0.0]],
    )
    vector_store.upsert_chunks(
        [{
            "id": "2:second",
            "text": "second restricted material",
            "metadata": {
                "document_id": "2",
                "content_hash": second_hash,
                "page_number": 1,
            },
        }],
        [[0.99, 0.01]],
    )
    hits = vector_store.search_chunks([1.0, 0.0], {1: first_hash}, 10)
    assert len(hits) == 1
    assert hits[0].metadata["document_id"] == "1"
