import hashlib
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.core.tokens import create_access_token, verify_access_token
from app.core.config import settings
from app.core.email_validation import validate_email, validate_password
from app.core.email_delivery import (
    EmailDeliveryError,
    reset_url,
    send_email,
    verification_url,
)
from app.models import AuditLog, AuthToken, User, UserRole, UserSession
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    ResendVerificationRequest,
    VerifyEmailRequest,
    EmailCheckRequest,
    EmailChangeRequest,
    TokenResponse,
    RegistrationResponse,
    UserResponse,
)
router = APIRouter(prefix="/api/auth", tags=["Authentication"])
bearer_scheme = HTTPBearer(auto_error=False)


_rate_lock = threading.Lock()
_rate_entries: dict[tuple[str, str], list[float]] = {}


def rate_limit(request: Request, action: str, limit: int, window_seconds: int = 3600) -> None:
    key = (request.client.host if request.client else "unknown", action)
    now = time.monotonic()
    with _rate_lock:
        recent = [timestamp for timestamp in _rate_entries.get(key, []) if now - timestamp < window_seconds]
        if len(recent) >= limit:
            raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
        recent.append(now)
        _rate_entries[key] = recent


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def audit_auth(db: Session, user: User, action: str) -> None:
    db.add(AuditLog(
        user_id=user.id,
        action=action,
        entity_type="user",
        entity_id=user.id,
    ))


def checked_email(email: str, allow_typo: bool = False) -> str:
    try:
        result = validate_email(email, allow_typo=allow_typo)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if result.suggestion:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Did you mean this email instead?",
                "suggested_email": result.suggestion,
                "entered_email": result.normalized,
            },
        )
    return result.normalized


def create_auth_token(db: Session, user: User, purpose: str) -> str:
    db.execute(
        update(AuthToken)
        .where(AuthToken.user_id == user.id, AuthToken.purpose == purpose, AuthToken.used_at.is_(None))
        .values(used_at=utc_now())
    )
    token = secrets.token_urlsafe(32)
    db.add(AuthToken(
        user_id=user.id,
        purpose=purpose,
        token_hash=token_hash(token),
        expires_at=utc_now() + (
            timedelta(days=7) if purpose == "lecturer_invite"
            else timedelta(minutes=10)
        ),
    ))
    db.flush()
    return token


def send_verification_email(db: Session, user: User) -> str | None:
    token = create_auth_token(db, user, "verify_email")
    link = verification_url(token)
    try:
        send_email(
            user.email,
            "Verify your StudyBridge AI email",
            f"Verify your email by opening this link: {link}\nThis link expires in 30 minutes.",
            f"<p>Verify your StudyBridge AI email.</p><p><a href=\"{link}\">Verify email address</a></p><p>This link expires in 30 minutes.</p>",
        )
    except EmailDeliveryError as exc:
        raise HTTPException(status_code=502, detail="Verification email could not be sent. Please use resend verification.") from exc
    return link if settings.EMAIL_MODE.lower() == "console" else None


@router.post("/email/check")
def check_email(data: EmailCheckRequest):
    try:
        result = validate_email(data.email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {
        "normalized_email": result.normalized,
        "suggested_email": result.suggestion,
        "dns_reachable": result.dns_reachable,
    }


@router.post("/register", response_model=RegistrationResponse, status_code=201)
def register_user(request: Request, data: RegisterRequest, db: Session = Depends(get_db)):
    rate_limit(request, "register", 5)
    email = checked_email(data.email, data.allow_email_typo)
    try:
        validate_password(data.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    existing_user = db.scalar(
        select(User).where(User.email == email)
    )
    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists.",
        )
    user = User(
        full_name=data.full_name.strip(),
        email=email,
        password_hash=hash_password(data.password),
        role=UserRole.STUDENT,
        email_verified=False,
    )
    db.add(user)
    db.flush()
    try:
        development_link = send_verification_email(db, user)
        audit_auth(db, user, "auth.registration.created")
        db.commit()
        db.refresh(user)
    except HTTPException:
        db.rollback()
        raise
    except EmailDeliveryError:
        db.rollback()
        raise HTTPException(status_code=502, detail="Verification email could not be sent. Please try registering again.")
    response = RegistrationResponse.model_validate(user)
    return response.model_copy(update={"development_verification_url": development_link})
@router.post("/login", response_model=TokenResponse)
def login_user(data: LoginRequest, db: Session = Depends(get_db)):
    email = checked_email(data.email, data.allow_email_typo)
    user = db.scalar(
        select(User).where(User.email == email)
    )
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password.",
        )
    if not user.email_verified:
        raise HTTPException(
            status_code=403,
            detail="Verify your email address before signing in.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="This account is inactive.",
        )
    session_id = secrets.token_urlsafe(32)
    session_hash_value = token_hash(session_id)
    session_record = UserSession(
        user_id=user.id,
        session_hash=session_hash_value,
        expires_at=utc_now() + timedelta(hours=24),
        created_at=utc_now(),
    )
    db.add(session_record)
    db.flush()
    audit_auth(db, user, "auth.login.succeeded")
    access_token = create_access_token(
        str(user.id),
        expires_delta=timedelta(hours=24),
        session_hash=session_hash_value,
    )
    db.commit()
    return TokenResponse(access_token=access_token)


@router.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    if len(token) < 20:
        raise HTTPException(status_code=400, detail="Invalid verification token.")
    record = db.scalar(
        select(AuthToken).where(
            AuthToken.purpose.in_(["verify_email", "email_change"]),
            AuthToken.token_hash == token_hash(token),
        )
    )
    if not record or record.used_at is not None:
        raise HTTPException(status_code=400, detail="Invalid verification token.")
    if record.expires_at <= utc_now():
        raise HTTPException(status_code=410, detail="Verification link has expired.")
    user = db.get(User, record.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid verification token.")
    if record.purpose == "email_change" and record.target_email:
        duplicate = db.scalar(select(User).where(User.email == record.target_email, User.id != user.id))
        if duplicate:
            raise HTTPException(status_code=409, detail="That email address is already in use.")
        user.email = record.target_email
        db.execute(update(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
        ).values(revoked_at=utc_now()))
    user.email_verified = True
    audit_auth(db, user, "auth.email.verified")
    record.used_at = utc_now()
    db.execute(
        update(AuthToken)
        .where(AuthToken.user_id == user.id, AuthToken.purpose.in_(["verify_email", "email_change"]), AuthToken.used_at.is_(None))
        .values(used_at=utc_now())
    )
    db.commit()
    return {"message": "Email address verified successfully."}


@router.post("/verification/resend")
def resend_verification(request: Request, data: ResendVerificationRequest, db: Session = Depends(get_db)):
    rate_limit(request, "verification_resend", 5)
    email = checked_email(data.email, data.allow_email_typo)
    user = db.scalar(select(User).where(User.email == email))
    development_link = None
    if user and not user.email_verified:
        try:
            development_link = send_verification_email(db, user)
            db.commit()
        except HTTPException as exc:
            raise exc
        except Exception:
            db.rollback()
            raise HTTPException(status_code=502, detail="Verification email could not be sent.")
    else:
        db.rollback()
    response: dict[str, str | None] = {
        "message": "If an unverified account exists, a verification email has been sent."
    }
    if settings.EMAIL_MODE.lower() == "console":
        response["development_verification_url"] = development_link
    return response


@router.post("/forgot-password")
def forgot_password(request: Request, data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    rate_limit(request, "forgot_password", 5)
    email = checked_email(data.email, data.allow_email_typo)
    user = db.scalar(select(User).where(User.email == email))
    if user:
        token = create_auth_token(db, user, "password_reset")
        link = reset_url(token)
        try:
            send_email(
                user.email,
                "Reset your StudyBridge AI password",
                f"Reset your password by opening this link: {link}\nThis link expires in 30 minutes.",
                f"<p>Reset your StudyBridge AI password.</p><p><a href=\"{link}\">Choose a new password</a></p><p>This link expires in 30 minutes.</p>",
            )
            db.commit()
        except EmailDeliveryError:
            db.rollback()
            raise HTTPException(status_code=502, detail="Password reset email could not be sent.")
    else:
        db.rollback()
    return {"message": "If an account exists for that email, password reset instructions have been sent."}


@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    try:
        validate_password(data.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    record = db.scalar(
        select(AuthToken).where(
            AuthToken.purpose == "password_reset",
            AuthToken.token_hash == token_hash(data.token),
        )
    )
    if not record or record.used_at is not None:
        raise HTTPException(status_code=400, detail="Invalid or already-used reset token.")
    if record.expires_at <= utc_now():
        raise HTTPException(status_code=410, detail="Password reset link has expired.")
    user = db.get(User, record.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid reset token.")
    user.password_hash = hash_password(data.password)
    audit_auth(db, user, "auth.password.reset")
    db.execute(update(UserSession).where(
        UserSession.user_id == user.id,
        UserSession.revoked_at.is_(None),
    ).values(revoked_at=utc_now()))
    record.used_at = utc_now()
    db.execute(
        update(AuthToken)
        .where(AuthToken.user_id == user.id, AuthToken.purpose == "password_reset", AuthToken.used_at.is_(None))
        .values(used_at=utc_now())
    )
    db.commit()
    return {"message": "Password reset successfully."}


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    payload = verify_access_token(credentials.credentials)
    if not payload:
        raise unauthorized
    try:
        user_id = int(payload["sub"])
    except (ValueError, TypeError):
        raise unauthorized
    user = db.get(User, user_id)
    if not user or not user.is_active or not user.email_verified:
        raise unauthorized
    session_hash_value = payload.get("sid")
    if session_hash_value:
        session_record = db.scalar(
            select(UserSession).where(
                UserSession.session_hash == session_hash_value,
                UserSession.user_id == user.id,
                UserSession.revoked_at.is_(None),
            )
        )
        if not session_record or session_record.expires_at <= utc_now():
            raise unauthorized
        session_record.last_seen_at = utc_now()
        db.commit()
    return user
@router.get("/me", response_model=UserResponse)
def get_my_account(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/logout")
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials:
        payload = verify_access_token(credentials.credentials)
        if payload and payload.get("sid"):
            db.execute(
                update(UserSession)
                .where(UserSession.session_hash == payload["sid"], UserSession.revoked_at.is_(None))
                .values(revoked_at=utc_now())
            )
            try:
                user = db.get(User, int(payload["sub"]))
            except (KeyError, TypeError, ValueError):
                user = None
            if user:
                audit_auth(db, user, "auth.logout")
            db.commit()
    return {"message": "Signed out."}


@router.post("/email/change")
def change_email(
    data: EmailChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(data.password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect password.")
    new_email = checked_email(data.email, data.allow_email_typo)
    if new_email == current_user.email:
        raise HTTPException(status_code=409, detail="This is already your current email address.")
    if db.scalar(select(User).where(User.email == new_email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    db.execute(
        update(AuthToken)
        .where(AuthToken.user_id == current_user.id, AuthToken.purpose == "email_change", AuthToken.used_at.is_(None))
        .values(used_at=utc_now())
    )
    token = create_auth_token(db, current_user, "email_change")
    record = db.scalar(select(AuthToken).where(AuthToken.token_hash == token_hash(token)))
    if record:
        record.target_email = new_email
    link = verification_url(token)
    try:
        send_email(
            new_email,
            "Confirm your StudyBridge AI email change",
            f"Confirm this email change by opening this link: {link}\nThis link expires in 30 minutes.",
            f"<p>Confirm your StudyBridge AI email change.</p><p><a href=\"{link}\">Confirm new email</a></p><p>This link expires in 30 minutes.</p>",
        )
        audit_auth(db, current_user, "auth.email_change.requested")
        db.commit()
    except EmailDeliveryError:
        db.rollback()
        raise HTTPException(status_code=502, detail="Email change confirmation could not be sent.")
    return {"message": "Confirmation sent. The email address changes after verification."}
