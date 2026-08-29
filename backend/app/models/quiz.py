from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy import String, Text, Integer, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    difficulty: Mapped[str] = mapped_column(String(50), default="MEDIUM", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="DRAFT", index=True, nullable=False)  # DRAFT, PUBLISHED, UNPUBLISHED, ARCHIVED
    time_per_question: Mapped[int] = mapped_column(Integer, default=30, nullable=False)  # in seconds
    maximum_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0 = unlimited
    scoring_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("admins.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)

    # Relationships
    creator = relationship("Admin", back_populates="quizzes")
    questions = relationship(
        "Question",
        back_populates="quiz",
        cascade="all, delete-orphan",
        order_by="Question.question_order",
    )
    sessions = relationship("QuizSession", back_populates="quiz", cascade="all, delete-orphan")
    results = relationship("QuizResult", back_populates="quiz", cascade="all, delete-orphan")
