from typing import Generator, Optional
from fastapi import Depends, HTTPException, status, Header, Query
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import decode_access_token, hash_session_token
from app.models.admin import Admin
from app.models.quiz_session import QuizSession

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admin/auth/login", auto_error=False)
http_bearer = HTTPBearer(auto_error=False)


def get_current_admin(
    token: Optional[str] = Depends(oauth2_scheme),
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer),
    token_query: Optional[str] = Query(None, alias="token"),
    db: Session = Depends(get_db),
) -> Admin:
    raw_token = token
    if not raw_token and auth_header:
        raw_token = auth_header.credentials
    if not raw_token and token_query:
        raw_token = token_query

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from app.core.config import settings
    if settings.DATABASE_BACKEND == "firestore":
        from app.core.firebase import verify_admin_identity
        identity = verify_admin_identity(raw_token)
        admin = db.query(Admin).filter(Admin.email == identity["email"].lower().strip()).first()
        if not admin or not admin.is_active:
            raise HTTPException(status_code=403, detail="Administrator account is not authorized")
        return admin

    payload = decode_access_token(raw_token)
    if not payload or payload.get("admin_auth_version") != 2:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    admin_id = payload.get("sub")
    if not admin_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject identifier",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        admin_id_int = int(admin_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token subject",
        )

    admin = db.query(Admin).filter(Admin.id == admin_id_int).first()
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin user not found",
        )
    if not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin account is deactivated",
        )

    return admin


def get_current_player_session(
    session_id: int,
    x_session_token: Optional[str] = Header(None, alias="X-Session-Token"),
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer),
    db: Session = Depends(get_db),
) -> QuizSession:
    raw_token = x_session_token
    if not raw_token and auth_header:
        raw_token = auth_header.credentials

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session authentication token required (provide via X-Session-Token or Bearer header)",
        )

    token_hash = hash_session_token(raw_token)
    session = db.query(QuizSession).filter(
        QuizSession.id == session_id,
        QuizSession.session_token_hash == token_hash,
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session or token",
        )

    return session
