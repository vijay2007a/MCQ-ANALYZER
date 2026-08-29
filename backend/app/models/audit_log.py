from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import String, Text, Integer, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    # Examples: ADMIN_LOGIN_SUCCESS, ADMIN_LOGIN_FAILED, QUIZ_CREATED, QUIZ_UPDATED,
    # QUIZ_DELETED, QUIZ_PUBLISHED, SUSPICIOUS_ACTIVITY, REPLAY_ATTEMPT,
    # OUT_OF_ORDER_SUBMISSION, SESSION_EXPIRED_SUBMISSION, IDOR_ATTEMPT, RATE_LIMIT_EXCEEDED
    
    actor_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ADMIN, PLAYER, ANONYMOUS, SYSTEM
    actor_id: Mapped[Optional[str]] = mapped_column(String(100), index=True, nullable=True)  # Admin ID, Session ID, or IP
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    resource_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # QUIZ, QUESTION, SESSION, RESULT, ADMIN
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)  # Safe metadata only, NO PASSWORDS/TOKENS
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True, nullable=False
    )
