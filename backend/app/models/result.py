from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class QuizResult(Base):
    __tablename__ = "quiz_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quiz_sessions.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    player_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    quiz_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    total_score: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    correct_answers: Mapped[int] = mapped_column(Integer, nullable=False)
    incorrect_answers: Mapped[int] = mapped_column(Integer, nullable=False)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    accuracy: Mapped[float] = mapped_column(Float, nullable=False)  # percentage, e.g. 75.0
    total_time_ms: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    average_response_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    # Relationships
    session = relationship("QuizSession", back_populates="result")
    quiz = relationship("Quiz", back_populates="results")
