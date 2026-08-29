from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class QuizSession(Base):
    __tablename__ = "quiz_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    session_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    quiz_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_question_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    current_question_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(50), default="ACTIVE", index=True, nullable=False
    )  # ACTIVE, COMPLETED, EXPIRED, ABANDONED
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    quiz = relationship("Quiz", back_populates="sessions")
    attempts = relationship(
        "QuizAttempt",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="QuizAttempt.question_order",
    )
    result = relationship("QuizResult", back_populates="session", uselist=False, cascade="all, delete-orphan")
