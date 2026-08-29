from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quiz_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_order: Mapped[int] = mapped_column(Integer, nullable=False)
    submitted_option: Mapped[str] = mapped_column(String(1), nullable=False)  # 'A', 'B', 'C', 'D'
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    response_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)  # server measured ms
    points_earned: Mapped[int] = mapped_column(Integer, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)

    # Relationships
    session = relationship("QuizSession", back_populates="attempts")
    question = relationship("Question", back_populates="attempts")

    __table_args__ = (
        UniqueConstraint("session_id", "question_id", name="uq_session_question"),
        UniqueConstraint("session_id", "idempotency_key", name="uq_session_idempotency"),
    )
