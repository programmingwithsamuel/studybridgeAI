import logging
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.api.dependencies import require_roles
from app.core.database import SessionLocal, get_db
from app.models import (
    ChatMessage,
    ChatSession,
    Document,
    DocumentIndexStatus,
    DocumentStatus,
    User,
    UserRole,
)
from app.schemas.chat import ChatMessageCreate, ChatSessionCreate
from app.services.academic_chat import (
    answer_question,
    decode_sources,
    encode_sources,
    prepare_answer,
)
from app.services.chat_provider import ChatProviderError, GeminiProvider
from app.services.document_indexing import process_approved_document

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["Academic Chat"])
AdminUser = Depends(require_roles(UserRole.ADMINISTRATOR))


def _owned_session(db: Session, user: User, session_id: int) -> ChatSession:
    session = db.scalar(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user.id,
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    return session


def _message_payload(message: ChatMessage) -> dict:
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
        "sources": decode_sources(message.sources_json),
    }


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def create_session(
    data: ChatSessionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = ChatSession(user_id=user.id, title=data.title.strip() if data.title else None)
    db.add(session)
    db.commit()
    db.refresh(session)
    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at.isoformat(),
        "message_count": 0,
    }


@router.get("/sessions")
def list_sessions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sessions = db.scalars(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.created_at.desc(), ChatSession.id.desc())
    ).all()
    return {"items": [{
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at.isoformat(),
        "message_count": db.query(ChatMessage).filter(
            ChatMessage.session_id == session.id
        ).count(),
    } for session in sessions]}


@router.get("/sessions/{session_id}")
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = _owned_session(db, user, session_id)
    messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at, ChatMessage.id)
    ).all()
    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at.isoformat(),
        "message_count": len(messages),
        "messages": [_message_payload(message) for message in messages],
    }


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = _owned_session(db, user, session_id)
    db.delete(session)
    db.commit()
    return {"message": "Chat session deleted."}


@router.post("/sessions/{session_id}/messages")
def send_message(
    session_id: int,
    data: ChatMessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = _owned_session(db, user, session_id)
    question = data.message.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Message cannot be blank.")
    try:
        answer, sources = answer_question(db, user, session.id, question)
    except ChatProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Academic chat retrieval failed for user %s.", user.id)
        raise HTTPException(
            status_code=503,
            detail="Academic retrieval is temporarily unavailable. Please try again.",
        ) from exc

    if session.title is None:
        session.title = question[:80]
    user_message = ChatMessage(
        session_id=session.id,
        role="user",
        content=question,
    )
    assistant_message = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=answer,
        sources_json=encode_sources(sources),
    )
    db.add_all([user_message, assistant_message])
    db.commit()
    db.refresh(user_message)
    db.refresh(assistant_message)
    return {
        "session_id": session.id,
        "user_message": _message_payload(user_message),
        "assistant_message": _message_payload(assistant_message),
        "answer": answer,
        "sources": decode_sources(assistant_message.sources_json),
    }


@router.post("/sessions/{session_id}/messages/stream")
def stream_message(
    session_id: int,
    data: ChatMessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = _owned_session(db, user, session_id)
    question = data.message.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Message cannot be blank.")

    if session.title is None:
        session.title = question[:80]
    user_message = ChatMessage(session_id=session.id, role="user", content=question)
    db.add(user_message)
    db.commit()
    db.refresh(user_message)
    user_payload = _message_payload(user_message)

    def events():
        yield f"data: {json.dumps({'type': 'start', 'user_message': user_payload})}\n\n"
        answer_parts: list[str] = []
        try:
            with SessionLocal() as chat_db:
                chat_user = chat_db.get(User, user.id)
                if chat_user is None:
                    raise ChatProviderError("Your account is no longer available.")
                quick_answer, sources, prompt = prepare_answer(
                    chat_db,
                    chat_user,
                    session_id,
                    question,
                    exclude_message_id=user_message.id,
                )

            if quick_answer is not None:
                answer_parts.append(quick_answer)
                yield f"data: {json.dumps({'type': 'delta', 'text': quick_answer})}\n\n"
            else:
                for text in GeminiProvider().stream(prompt or ""):
                    answer_parts.append(text)
                    yield f"data: {json.dumps({'type': 'delta', 'text': text})}\n\n"

            answer = "".join(answer_parts).strip()
            if not answer:
                raise ChatProviderError("Gemini returned an empty response.")

            with SessionLocal() as chat_db:
                owned = chat_db.scalar(
                    select(ChatSession).where(
                        ChatSession.id == session_id,
                        ChatSession.user_id == user.id,
                    )
                )
                if owned is None:
                    raise ChatProviderError("Chat session no longer exists.")
                assistant_message = ChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content=answer,
                    sources_json=encode_sources(sources),
                )
                chat_db.add(assistant_message)
                chat_db.commit()
                chat_db.refresh(assistant_message)
                assistant_payload = _message_payload(assistant_message)

            yield f"data: {json.dumps({'type': 'done', 'assistant_message': assistant_payload}, ensure_ascii=False)}\n\n"
        except ChatProviderError as exc:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"
        except Exception:
            logger.exception("Streamed academic chat failed for user %s.", user.id)
            yield f"data: {json.dumps({'type': 'error', 'detail': 'The study assistant is temporarily unavailable. Please try again.'})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/indexing")
def list_index_status(
    db: Session = Depends(get_db),
    _admin: User = AdminUser,
):
    rows = db.execute(
        select(DocumentIndexStatus, Document.title, Document.status, Document.sha256)
        .join(Document, Document.id == DocumentIndexStatus.document_id)
        .order_by(DocumentIndexStatus.updated_at.desc())
    ).all()
    return {"items": [{
        "document_id": state.document_id,
        "document_title": title,
        "document_status": document_status.value,
        "content_hash": state.content_hash,
        "current_content_hash": content_hash,
        "status": state.status,
        "error": state.error,
        "indexed_at": state.indexed_at.isoformat() if state.indexed_at else None,
        "updated_at": state.updated_at.isoformat(),
    } for state, title, document_status, content_hash in rows]}


@router.post("/indexing/{document_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_indexing(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _admin: User = AdminUser,
):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if document.status != DocumentStatus.VERIFIED or document.withdrawn_at is not None:
        raise HTTPException(status_code=409, detail="Only active approved documents can be indexed.")
    background_tasks.add_task(process_approved_document, document.id)
    return {"message": "Indexing retry queued.", "document_id": document.id}


@router.post("/indexing/retry-failed", status_code=status.HTTP_202_ACCEPTED)
def retry_failed_indexing(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _admin: User = AdminUser,
):
    documents = db.scalars(
        select(Document)
        .join(DocumentIndexStatus, DocumentIndexStatus.document_id == Document.id)
        .where(
            DocumentIndexStatus.status == "failed",
            Document.status == DocumentStatus.VERIFIED,
            Document.withdrawn_at.is_(None),
        )
    ).all()
    for document in documents:
        background_tasks.add_task(process_approved_document, document.id)
    return {"message": "Failed indexing jobs queued.", "count": len(documents)}