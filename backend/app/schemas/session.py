import html
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict
from app.schemas.question import QuestionPlayerResponse


class StartQuizRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_name: str = Field(..., min_length=2, max_length=50)

    @field_validator("player_name")
    @classmethod
    def sanitize_player_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Player name cannot be empty or only spaces")
        # Sanitize HTML tags to prevent stored XSS
        return html.escape(cleaned)


class StartQuizResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: int
    session_token: str
    quiz_id: int
    quiz_title: str
    time_per_question: int
    started_at: datetime
    expires_at: datetime
    total_questions: int
    first_question: Optional[QuestionPlayerResponse] = None


class SubmitAnswerRequest(BaseModel):
    """
    CRITICAL: Untrusted payload.
    Enforces extra='forbid' so students cannot send fake score, points, or elapsed_time fields.
    """
    model_config = ConfigDict(extra="forbid")

    question_order: int = Field(..., ge=1)
    selected_option: str = Field(..., min_length=1, max_length=1)
    idempotency_key: str = Field(..., min_length=8, max_length=100)

    @field_validator("selected_option")
    @classmethod
    def validate_option(cls, v: str) -> str:
        v_upper = v.upper()
        if v_upper not in ["A", "B", "C", "D"]:
            raise ValueError("Selected option must be one of: A, B, C, D")
        return v_upper


class SubmitAnswerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_correct: bool
    points_earned: int
    response_time_ms: int
    correct_option: str
    explanation: str
    current_score: int
    is_quiz_completed: bool
    next_question_available: bool
    next_question: Optional[QuestionPlayerResponse] = None


class SessionStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: int
    status: str
    player_name: str
    quiz_id: int
    quiz_title: str
    current_question_order: int
    total_questions: int
    is_completed: bool
    started_at: datetime
    expires_at: datetime


class PlayerEventRequest(BaseModel):
    """
    Schema for logging anti-cheating, clipboard, and security telemetry events.
    """
    model_config = ConfigDict(extra="ignore")

    event_type: str = Field(..., min_length=2, max_length=100)
    question_order: Optional[int] = Field(None, ge=1)
    details: Optional[dict] = Field(default_factory=dict)


class PlayerEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    event_type: str
    recorded_at: datetime
